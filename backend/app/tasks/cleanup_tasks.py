from celery import Celery
from datetime import datetime, timedelta
from sqlalchemy import select
from sqlalchemy.orm import Session
import os
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
        'cleanup-soft-deleted-items-weekly': {
            'task': 'app.tasks.cleanup_tasks.cleanup_soft_deleted_items',
            'schedule': 604800.0,  # 7 days in seconds (weekly)
        },
        'recalculate-all-users-storage': {
            'task': 'app.tasks.cleanup_tasks.recalculate_all_users_storage',
            'schedule': settings.STORAGE_RECALCULATION_PERIOD,  # Configurable period
        },
    },
)


@celery_app.task(bind=True, max_retries=3)
def cleanup_soft_deleted_items(self):
    """Clean up soft-deleted items older than 30 days."""
    try:
        logger.info("Starting cleanup of soft-deleted items older than 30 days")
        
        # Get database session
        db = next(get_db())
        
        try:
            folder_repo = FolderRepository(db)
            file_repo = FileRepository(db)
            
            # Calculate cutoff date (30 days ago)
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            total_folders_deleted = 0
            total_files_deleted = 0
            total_size_freed = 0
            
            # Get soft-deleted folders older than 30 days
            old_folders = db.execute(
                select(Folder).where(
                    Folder.deleted_at.isnot(None),
                    Folder.deleted_at < cutoff_date
                )
            ).scalars().all()
            
            for folder in old_folders:
                # Hard delete folder
                folder_size = folder.size
                folder_repo.hard_delete(folder.uuid)
                total_folders_deleted += 1
                total_size_freed += folder_size
                logger.info(f"Hard deleted folder: {folder.uuid} (size: {folder_size})")
            
            # Get soft-deleted files older than 30 days
            old_files = db.execute(
                select(File).where(
                    File.deleted_at.isnot(None),
                    File.deleted_at < cutoff_date
                )
            ).scalars().all()
            
            for file in old_files:
                # Delete actual file from storage
                file_path = os.path.join(settings.STORAGE_BASE_PATH, file.uuid)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted file from storage: {file_path}")

                # Hard delete file record
                file_repo.hard_delete(file.uuid)
                total_files_deleted += 1
                total_size_freed += file.size
                logger.info(f"Hard deleted file: {file.uuid} (size: {file.size})")
            
            logger.info(
                f"Cleanup completed: {total_folders_deleted} folders, "
                f"{total_files_deleted} files, {total_size_freed} bytes freed"
            )
            
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
            from app.services.account_service import AccountService
            from app.models.file import File
            from app.models.folder import Folder
            from sqlalchemy import select
            
            account_repo = AccountRepository(db)
            file_repo = FileRepository(db)
            folder_repo = FolderRepository(db)
            account_service = AccountService(account_repo)
            
            # Get all users
            all_users = account_repo.get_all()
            
            total_users_processed = 0
            total_folders_updated = 0
            
            for user in all_users:
                logger.info(f"Processing user: {user.username}")
                
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
                
                logger.info(f"Updated user {user.username}: {user_total_size} bytes, {len(folders)} folders")
            
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
