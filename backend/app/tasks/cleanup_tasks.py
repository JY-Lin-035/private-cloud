from celery import Celery
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
import os
import shutil
import time
import platform
import logging

from app.config import settings
from app.models.folder import Folder
from app.models.file import File
from app.repositories.folder_repository import FolderRepository
from app.repositories.file_repository import FileRepository
from app.api.dependencies import get_db

logger = logging.getLogger(__name__)

# 建立 Celery App
celery_app = Celery(
    'cleanup_tasks',
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

# 根據作業系統自動調整配置
if platform.system() == 'Windows':
    worker_pool = 'solo'
else:
    worker_pool = 'prefork'

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    task_always_eager=False,
    worker_pool=worker_pool,
    worker_prefetch_multiplier=1,
    beat_schedule={
        'cleanup-soft-deleted-items': {
            'task': 'app.tasks.cleanup_tasks.cleanup_soft_deleted_items',
            'schedule': settings.TRASH_CLEANUP_INTERVAL_SECONDS,
            'options': {'queue': 'cleanup'},
        },
        'recalculate-all-users-storage': {
            'task': 'app.tasks.cleanup_tasks.recalculate_all_users_storage',
            'schedule': settings.STORAGE_RECALCULATION_PERIOD,
            'options': {'queue': 'cleanup'},
        },
        'cleanup-stale-tus-uploads': {
            'task': 'app.tasks.cleanup_tasks.cleanup_stale_tus_uploads',
            'schedule': 3600,
            'options': {'queue': 'cleanup'},
        },
    },
)


def _file_storage_path(file) -> str:
    """Resolve the physical storage path for a file row."""
    return file.storage_path or os.path.join(settings.STORAGE_BASE_PATH, file.uuid)


def _purge_folder_subtree(db, file_repo, folder_uuid: str) -> tuple[int, int]:
    """Recursively delete a folder subtree: physical files first, then rows.

    Returns (files_removed, bytes_freed). Deleting the DB rows without this
    walk would let the FK CASCADE silently drop child File rows and orphan
    their physical files on disk forever.
    """
    from app.repositories.folder_repository import FolderRepository
    folder_repo = FolderRepository(db)

    files_removed = 0
    bytes_freed = 0

    child_folders = db.execute(
        select(Folder).where(Folder.parent_id == folder_uuid)
    ).scalars().all()
    for child in child_folders:
        f, b = _purge_folder_subtree(db, file_repo, child.uuid)
        files_removed += f
        bytes_freed += b

    child_files = db.execute(
        select(File).where(File.parent_folder_id == folder_uuid)
    ).scalars().all()
    for child_file in child_files:
        path = _file_storage_path(child_file)
        if os.path.exists(path):
            os.remove(path)
        _purge_collab(child_file.uuid)
        file_repo.hard_delete(child_file.uuid)
        files_removed += 1
        bytes_freed += child_file.size or 0

    return files_removed, bytes_freed


def _purge_collab(file_uuid: str) -> None:
    """Drop collaboration Redis state and close any live socket for a file."""
    try:
        from redis import Redis
        from app.services import collab_events
        from app.services.snapshot_service import purge_file_state
        collab_events.revoke_file(file_uuid, "retention purge")
        r = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        try:
            purge_file_state(file_uuid, r)
        finally:
            r.close()
    except Exception:
        pass


@celery_app.task(bind=True, max_retries=3)
def cleanup_soft_deleted_items(self):
    """Hard delete soft-deleted files/folders older than the retention period."""
    try:
        retention = settings.TRASH_RETENTION_DAYS
        logger.info(f"Starting cleanup of soft-deleted items older than {retention} days")
        
        # Get database session
        db = next(get_db())
        
        try:
            folder_repo = FolderRepository(db)
            file_repo = FileRepository(db)
            
            # Calculate cutoff date
            cutoff_date = datetime.utcnow() - timedelta(days=retention)
            
            total_folders_deleted = 0
            total_files_deleted = 0
            total_size_freed = 0
            
            # Purge soft-deleted folders older than cutoff, including their
            # whole subtree (children may share the parent's deleted_at)
            old_folders = db.execute(
                select(Folder).where(
                    Folder.deleted_at.isnot(None),
                    Folder.deleted_at < cutoff_date
                )
            ).scalars().all()
            
            for folder in old_folders:
                if not db.get(Folder, folder.id):
                    continue  # already purged as part of an ancestor's subtree
                f, b = _purge_folder_subtree(db, file_repo, folder.uuid)
                folder_repo.hard_delete(folder.uuid)
                total_folders_deleted += 1
                total_files_deleted += f
                total_size_freed += b
                logger.info(f"Purged folder {folder.uuid} with {f} files ({b} bytes)")
            
            # Delete remaining soft-deleted loose files older than cutoff
            old_files = db.execute(
                select(File).where(
                    File.deleted_at.isnot(None),
                    File.deleted_at < cutoff_date
                )
            ).scalars().all()
            
            for file in old_files:
                file_path = _file_storage_path(file)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted file from storage: {file_path}")

                _purge_collab(file.uuid)
                file_repo.hard_delete(file.uuid)
                total_files_deleted += 1
                total_size_freed += file.size or 0
            
            logger.info(
                f"Cleanup completed: {total_folders_deleted} folders, "
                f"{total_files_deleted} files, {total_size_freed} bytes freed"
            )
            
            # Reconcile used_size accounting after physical removals
            recalculate_all_users_storage.apply_async(queue='cleanup')
            
            return {
                "status": "success",
                "folders_deleted": total_folders_deleted,
                "files_deleted": total_files_deleted,
                "size_freed": total_size_freed
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Cleanup task failed: {str(e)}")
        return {"status": "error", "error": str(e)}


@celery_app.task(bind=True, max_retries=3)
def recalculate_all_users_storage(self):
    """Recalculate storage usage for all users."""
    try:
        logger.info("Starting storage recalculation for all users")
        
        # Get database session
        db = next(get_db())
        
        try:
            from app.repositories.account_repository import AccountRepository
            from app.repositories.file_repository import FileRepository
            from app.repositories.folder_repository import FolderRepository
            from app.models.file import File
            from app.models.folder import Folder
            from sqlalchemy import select
            
            account_repo = AccountRepository(db)
            file_repo = FileRepository(db)
            folder_repo = FolderRepository(db)
            
            # Get all users
            all_users = account_repo.get_all()
            
            total_users_processed = 0
            total_folders_updated = 0
            
            for user in all_users:
                logger.info(f"Processing user: {user.name}")
                
                # Get all folders for the user
                folders = db.execute(
                    select(Folder).where(Folder.owner_id == user.id)
                ).scalars().all()
                
                user_total_size = 0
                
                # Recalculate each folder size
                for folder in folders:
                    # Calculate actual size from files in this folder
                    files = db.execute(
                        select(File).where(
                            File.parent_folder_id == folder.uuid,
                            File.deleted_at.is_(None)
                        )
                    ).scalars().all()
                    
                    actual_size = sum(file.size for file in files)
                    
                    # Update folder size
                    folder.size = actual_size
                    user_total_size += actual_size
                
                # Update account used size
                user.used_size = user_total_size
                
                total_users_processed += 1
                total_folders_updated += len(folders)
                
                logger.info(f"Updated user {user.name}: {user_total_size} bytes, {len(folders)} folders")
            
            db.commit()
            
            logger.info(
                f"Storage recalculation completed: {total_users_processed} users, "
                f"{total_folders_updated} folders updated"
            )
            
            return {
                "status": "success",
                "users_processed": total_users_processed,
                "folders_updated": total_folders_updated
            }
            
        finally:
            db.close()
            
    except Exception as e:
        logger.error(f"Storage recalculation task failed: {str(e)}")
        return {"status": "error", "error": str(e)}


@celery_app.task(bind=True, max_retries=3)
def cleanup_stale_tus_uploads(self):
    """Remove abandoned tus temp upload directories past the max age."""
    try:
        max_age = settings.TUS_TEMP_MAX_AGE_SECONDS
        base = settings.STORAGE_BASE_PATH
        if not os.path.isabs(base):
            base = os.path.join(os.getcwd(), base)
        from app.constants import StorageLimits
        tus_dir = os.path.join(base, StorageLimits.TUS_TEMP_DIR_NAME)
        cutoff = time.time() - max_age
        removed = 0
        if os.path.isdir(tus_dir):
            for name in os.listdir(tus_dir):
                path = os.path.join(tus_dir, name)
                try:
                    if not os.path.isdir(path):
                        continue
                    # Age on the newest file inside, NOT the directory mtime:
                    # appending chunks to upload.bin does not refresh the dir
                    # mtime, so a >24h slow-but-active upload would otherwise
                    # be deleted mid-flight.
                    newest = os.path.getmtime(path)
                    for root, _dirs, files in os.walk(path):
                        for fn in files:
                            try:
                                newest = max(newest, os.path.getmtime(os.path.join(root, fn)))
                            except OSError:
                                continue
                    if newest < cutoff:
                        shutil.rmtree(path, ignore_errors=True)
                        removed += 1
                except OSError:
                    continue
        # GC orphaned collab temp files (<uuid>.<pid>.<hex>.tmp in the storage
        # root) left behind by crashed persist writes. Real blobs never carry
        # the .tmp suffix.
        pruned = 0
        try:
            for name in os.listdir(base):
                if not name.endswith(".tmp"):
                    continue
                fp = os.path.join(base, name)
                try:
                    if os.path.isfile(fp) and os.path.getmtime(fp) < cutoff:
                        os.remove(fp)
                        pruned += 1
                except OSError:
                    continue
        except OSError:
            pass
        logger.info(f"Stale tus cleanup removed {removed} dirs, pruned {pruned} orphan tmp files")
        return {"status": "success", "removed": removed, "pruned_tmp": pruned}
    except Exception as e:
        logger.error(f"Stale tus cleanup failed: {str(e)}")
        return {"status": "error", "error": str(e)}
