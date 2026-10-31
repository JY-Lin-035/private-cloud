import uuid
import os
from datetime import datetime, timezone, timedelta

_tz_utc8 = timezone(timedelta(hours=8))

def _fmt_utc8(dt: datetime) -> str:
    if dt is None:
        return ''
    return dt.replace(tzinfo=timezone.utc).astimezone(_tz_utc8).strftime('%Y-%m-%d %H:%M:%S')
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.account import Account
from app.models.folder import Folder
from app.models.file import File
from app.repositories.account_repository import AccountRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.file_repository import FileRepository
from app.constants import HTTPStatus
from app.utils.name_validation import validate_display_name
from app.config import settings


class FolderService:
    def __init__(self, db: Session):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.folder_repo = FolderRepository(db)
        self.file_repo = FileRepository(db)
        self.storage_base_path = settings.STORAGE_BASE_PATH
    
    def _validate_folder_name(self, name: str) -> bool:
        """Validate folder name against the shared denylist (symbols allowed)."""
        _, error = validate_display_name(name)
        return error is None
    
    def _update_parent_folder_size(self, folder_uuid: str, size_delta: int, owner_id: Optional[int] = None):
        """Propagate a size delta up the ancestor chain (iterative, capped).

        Iteration (not recursion) removes the RecursionError DoS at extreme
        depths; the hop cap plus owner-stickiness means a corrupted or
        cross-owner chain can never loop forever or charge a foreign tree.
        """
        if not folder_uuid:
            return
        seen = set()
        cur_uuid = folder_uuid
        hops = 0
        chain_owner = owner_id
        while cur_uuid and hops < 64:
            if cur_uuid in seen:  # cycle guard
                return
            seen.add(cur_uuid)
            folder = self.folder_repo.get_by_uuid(cur_uuid)
            if not folder:
                return
            if chain_owner is None:
                chain_owner = folder.owner_id  # anchor propagation to this tree's owner
            if folder.owner_id != chain_owner:
                return  # never mutate another owner's chain
            folder.size = max(0, (folder.size or 0) + size_delta)
            self.folder_repo.update(folder)
            cur_uuid = folder.parent_id
            hops += 1
    
    def _soft_delete_children(self, folder_uuid: str):
        """Iteratively soft-delete all descendants (cycle-safe, no recursion)."""
        from collections import deque
        file_repo = FileRepository(self.db)
        seen = {folder_uuid}
        q = deque([folder_uuid])
        while q:
            cur = q.popleft()
            child_folders = self.folder_repo.get_by_parent(cur)
            for child_folder in child_folders:
                if child_folder.uuid in seen:
                    continue
                seen.add(child_folder.uuid)
                q.append(child_folder.uuid)
                self.folder_repo.soft_delete(child_folder.uuid)
            for child_file in file_repo.get_by_folder(cur):
                file_repo.soft_delete(child_file.uuid)
    
    def _hard_delete_children(self, folder_uuid: str) -> None:
        """Iteratively hard-delete all descendants + their storage files.

        Cycle-safe and recursion-free (DS2: >64 depth used to blow the stack
        mid-delete, skipping the account.used_size decrement => quota drift).
        Only responsible for deletion, not size calculation.
        """
        from collections import deque
        file_repo = FileRepository(self.db)

        # Collect every descendant folder uuid (BFS, seen-guarded)
        order = []
        seen = {folder_uuid}
        q = deque([folder_uuid])
        while q:
            cur = q.popleft()
            for kid in self.db.execute(select(Folder.uuid).where(Folder.parent_id == cur)).scalars().all():
                if kid in seen:
                    continue
                seen.add(kid)
                order.append(kid)
                q.append(kid)

        # Delete all files under root + descendants
        parent_ids = [folder_uuid] + order
        for pid in parent_ids:
            for cf in self.db.execute(select(File).where(File.parent_folder_id == pid)).scalars().all():
                fp = os.path.join(self.storage_base_path, cf.uuid)
                try:
                    if os.path.exists(fp):
                        os.remove(fp)
                except OSError:
                    pass
                file_repo.hard_delete(cf.uuid)

        # Delete descendant folders (deepest-first is irrelevant for hard rows)
        for kid in order:
            self.folder_repo.hard_delete(kid)
    
    def create(self, user_id: int, parent_folder_uuid: Optional[str], name: str) -> Optional[Dict[str, Any]]:
        """Create a new folder."""
        try:
            # Validate folder name
            if not self._validate_folder_name(name):
                return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}
            
            # Check if account exists
            account = self.account_repo.get_by_id(user_id)
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            # Check if parent folder exists (if provided)
            if parent_folder_uuid:
                parent_folder = self.folder_repo.get_by_uuid(parent_folder_uuid)
                if not parent_folder or parent_folder.owner_id != user_id:
                    return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}
                if len(self._ancestor_chain(parent_folder)) + 1 > self.MAX_FOLDER_DEPTH:
                    return {'error': '資料夾深度過深', 'stateCode': HTTPStatus.BAD_REQUEST}
            
            # Check for duplicate folder name in same parent directory
            # (DB collation is case-insensitive; .first() tolerates legacy dupes)
            existing_folder = self.db.execute(
                select(Folder).where(
                    Folder.owner_id == user_id,
                    Folder.parent_id == parent_folder_uuid,
                    Folder.name == name,
                    Folder.deleted_at.is_(None)
                )
            ).scalars().first()
            
            if existing_folder:
                return {'error': '資料夾已存在', 'stateCode': HTTPStatus.BAD_REQUEST}
            
            # Create new folder
            new_folder = Folder(
                uuid=str(uuid.uuid4()),
                owner_id=user_id,
                parent_id=parent_folder_uuid,
                name=name,
                size=0
            )
            
            created_folder = self.folder_repo.create_with_uuid_retry(new_folder)
            
            # Update parent folder size (folder size is 0 initially)
            if parent_folder_uuid:
                self._update_parent_folder_size(parent_folder_uuid, 0)
            
            return {
                'uuid': created_folder.uuid,
                'name': created_folder.name,
                'created_at': _fmt_utc8(created_folder.created_at)
            }
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def rename(self, user_id: int, folder_uuid: str, new_name: str) -> Optional[Dict[str, Any]]:
        """Rename a folder."""
        try:
            # Validate folder name
            if not self._validate_folder_name(new_name):
                return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}
            
            # Get folder
            folder = self.folder_repo.get_by_uuid(folder_uuid)
            if not folder or folder.owner_id != user_id:
                return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}

            if folder.is_system:
                return {'error': '系統資料夾不可重命名', 'stateCode': HTTPStatus.FORBIDDEN}

            # Case-insensitive sibling collision guard (MySQL CI collation +
            # red-team F3): renaming onto a sibling that differs only by case
            # creates ambiguous rows that later blow up as 500s.
            siblings = self.db.execute(
                select(Folder.name).where(
                    Folder.parent_id == folder.parent_id,
                    Folder.owner_id == user_id,
                    Folder.deleted_at.is_(None),
                    Folder.uuid != folder.uuid,
                )
            ).scalars().all()
            if new_name.casefold() in {s.casefold() for s in siblings}:
                return {'error': '同名(不分大小寫)的資料夾已存在', 'stateCode': HTTPStatus.CONFLICT}

            # Update name
            folder.name = new_name
            self.folder_repo.update(folder)
            
            return {
                'uuid': folder.uuid,
                'name': folder.name,
                'updated_at': _fmt_utc8(folder.updated_at)
            }
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def delete(self, user_id: int, folder_uuid: str, permanent: bool = False) -> Optional[Dict[str, Any]]:
        """Delete a folder (soft or hard)."""
        try:
            account = self.account_repo.get_by_id(user_id)
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}

            folder = self.folder_repo.get_by_uuid(folder_uuid)
            if not folder or folder.owner_id != user_id:
                return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}

            # Prevent deletion of system folders (e.g., Home)
            if folder.is_system:
                return {'error': '系統資料夾無法刪除', 'stateCode': HTTPStatus.FORBIDDEN}

            folder_size = folder.size
            affected_files = self._collect_subtree_file_uuids(folder_uuid)

            if permanent:
                # Hard delete: recursively delete all children and storage files
                self._hard_delete_children(folder_uuid)
                self.folder_repo.hard_delete(folder_uuid)

                # Update account used size only on hard delete (folder size already includes all children)
                account.used_size = max(0, account.used_size - folder_size)
                self.account_repo.update(account)

                # Update parent folder size with folder size (already includes all children)
                if folder.parent_id:
                    self._update_parent_folder_size(folder.parent_id, -folder_size)
            else:
                # Soft delete: recursively mark all children as deleted
                self._soft_delete_children(folder_uuid)
                self.folder_repo.soft_delete(folder_uuid)

                # Don't update parent folder size for soft delete (items still occupy space)

            try:
                from app.services import collab_events
                for fu in affected_files:
                    collab_events.revoke_file(fu, "folder deleted")
                if permanent:
                    from app.services.snapshot_service import purge_file_state
                    from redis import Redis as _Redis
                    _r = _Redis.from_url(settings.REDIS_URL, decode_responses=True)
                    try:
                        for fu in affected_files:
                            purge_file_state(fu, _r)
                    finally:
                        _r.close()
            except Exception:
                pass

            return {
                'uuid': folder_uuid,
                'size': folder_size,
                'permanent': permanent
            }
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def _collect_subtree_file_uuids(self, folder_uuid: str) -> set:
        """All file uuids anywhere under a folder (iterative, cycle-safe)."""
        try:
            from collections import deque
            files = set()
            seen = {folder_uuid}
            q = deque([folder_uuid])
            while q:
                cur = q.popleft()
                files |= set(self.db.execute(select(File.uuid).where(File.parent_folder_id == cur)).scalars().all())
                for kid in self.db.execute(select(Folder.uuid).where(Folder.parent_id == cur)).scalars().all():
                    if kid not in seen:
                        seen.add(kid); q.append(kid)
            return files
        except Exception:
            return set()
    
    def restore(self, user_id: int, folder_uuid: str) -> Optional[Dict[str, Any]]:
        """Restore a soft-deleted folder."""
        try:
            folder = self.db.execute(
                select(Folder).where(Folder.uuid == folder_uuid)
            ).scalar_one_or_none()
            
            if not folder or folder.owner_id != user_id:
                return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}
            
            if not folder.deleted_at:
                return {'error': 'Folder not deleted', 'stateCode': HTTPStatus.BAD_REQUEST}

            # DS2-2/F5: restoring under a still-trashed parent used to create an
            # invisible orphan (batch path had no guard at all). Fix by walking
            # the ancestor chain and restoring trashed ancestors too, so the
            # item always returns to a visible tree. Bounded by a seen-set.
            anc = folder.parent_id
            aseen = {folder.uuid}
            while anc and anc not in aseen:
                aseen.add(anc)
                p = self.folder_repo.get_by_uuid(anc)
                if not p:
                    break
                if p.deleted_at is not None:
                    p.deleted_at = None
                    self.folder_repo.update(p)
                anc = p.parent_id

            # Restore descendants iteratively (recursion blew the stack on deep trees)
            from collections import deque
            rq = deque([folder_uuid])
            rseen = {folder_uuid}
            while rq:
                cur = rq.popleft()
                for cf in self.db.execute(select(Folder).where(Folder.parent_id == cur)).scalars().all():
                    cf.deleted_at = None
                    if cf.uuid not in rseen:
                        rseen.add(cf.uuid); rq.append(cf.uuid)
                for cfile in self.db.execute(select(File).where(File.parent_folder_id == cur)).scalars().all():
                    cfile.deleted_at = None
            self.db.flush()
            
            # Check for conflict with active folder having same name
            # Handle NULL parent_id comparison correctly
            if folder.parent_id is None:
                conflict_folder = self.db.execute(
                    select(Folder).where(
                        Folder.owner_id == user_id,
                        Folder.parent_id.is_(None),
                        Folder.name == folder.name,
                        Folder.deleted_at.is_(None)
                    )
                ).scalar_one_or_none()
            else:
                conflict_folder = self.db.execute(
                    select(Folder).where(
                        Folder.owner_id == user_id,
                        Folder.parent_id == folder.parent_id,
                        Folder.name == folder.name,
                        Folder.deleted_at.is_(None)
                    )
                ).scalar_one_or_none()
            
            if conflict_folder:
                # Merge soft-deleted folder into active folder
                try:
                    file_repo = FileRepository(self.db)
                    
                    total_moved_size = 0
                    
                    # Get existing file names in active folder to check for conflicts
                    active_files = self.db.execute(
                        select(File).where(
                            File.parent_folder_id == conflict_folder.uuid,
                            File.deleted_at.is_(None)
                        )
                    ).scalars().all()
                    active_file_names = {f.name for f in active_files}
                    
                    # Move all files from soft-deleted folder to active folder
                    child_files = self.db.execute(
                        select(File).where(File.parent_folder_id == folder_uuid)
                    ).scalars().all()
                    
                    for child_file in child_files:
                        # Check for name conflict
                        if child_file.name in active_file_names:
                            # Rename soft-deleted file with (1) suffix
                            name_parts = child_file.name.rsplit('.', 1)
                            if len(name_parts) == 2:
                                # Has extension
                                child_file.name = f"{name_parts[0]} (1).{name_parts[1]}"
                            else:
                                # No extension
                                child_file.name = f"{child_file.name} (1)"
                        
                        # Update parent_id to point to active folder
                        child_file.parent_folder_id = conflict_folder.uuid
                        
                        # Restore the file (clear deleted_at)
                        child_file.deleted_at = None
                        
                        total_moved_size += child_file.size
                    
                    # Get existing folder names in active folder to check for conflicts
                    active_folders = self.db.execute(
                        select(Folder).where(
                            Folder.parent_id == conflict_folder.uuid,
                            Folder.deleted_at.is_(None)
                        )
                    ).scalars().all()
                    active_folder_names = {f.name for f in active_folders}
                    
                    # Move all first-level subfolders from soft-deleted folder to active folder
                    child_folders = self.db.execute(
                        select(Folder).where(Folder.parent_id == folder_uuid)
                    ).scalars().all()
                    
                    for child_folder in child_folders:
                        # Check for name conflict with existing folders in target
                        existing_in_target = self.db.execute(
                            select(Folder).where(
                                Folder.parent_id == conflict_folder.uuid,
                                Folder.name == child_folder.name,
                                Folder.deleted_at.is_(None)
                            )
                        ).scalar_one_or_none()
                        
                        if existing_in_target:
                            # Rename soft-deleted folder with (1) suffix
                            child_folder.name = f"{child_folder.name} (1)"
                        
                        # Update parent_id to point to active folder
                        child_folder.parent_id = conflict_folder.uuid
                        # Restore the child folder (clear deleted_at)
                        child_folder.deleted_at = None
                    
                    # Update conflict folder size to include merged content
                    conflict_folder.size += total_moved_size
                    
                    # Permanently delete the soft-deleted folder after merge
                    
                    self.db.commit()
                    self.folder_repo.hard_delete(folder_uuid)
                    
                    return {
                        'uuid': conflict_folder.uuid,
                        'message': '資料夾已合併',
                        'merged_size': total_moved_size
                    }
                except Exception as e:
                    self.db.rollback()
                    return {'error': '合併失敗', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
            
            # No conflict, proceed with normal restore
            # Restore the folder (clear deleted_at)
            folder.deleted_at = None
            
            # Restore all children
            file_repo = FileRepository(self.db)
            
            # Get existing file names in this folder to check for conflicts
            existing_files = self.db.execute(
                select(File).where(
                    File.parent_folder_id == folder_uuid,
                    File.deleted_at.is_(None)
                )
            ).scalars().all()
            existing_file_names = {f.name for f in existing_files}
            
            # Get existing folder names in this folder to check for conflicts
            existing_folders = self.db.execute(
                select(Folder).where(
                    Folder.parent_id == folder_uuid,
                    Folder.deleted_at.is_(None)
                )
            ).scalars().all()
            existing_folder_names = {f.name for f in existing_folders}
            
            child_folders = self.db.execute(
                select(Folder).where(Folder.parent_id == folder_uuid)
            ).scalars().all()
            
            for child_folder in child_folders:
                # Check for name conflict with existing folders
                if child_folder.name in existing_folder_names:
                    # Rename folder with (1) suffix
                    child_folder.name = f"{child_folder.name} (1)"
                
                # Restore the child folder (clear deleted_at)
                child_folder.deleted_at = None
            
            child_files = self.db.execute(
                select(File).where(File.parent_folder_id == folder_uuid)
            ).scalars().all()
            
            for child_file in child_files:
                # Check for name conflict with existing files
                if child_file.name in existing_file_names:
                    # Rename file with (1) suffix
                    name_parts = child_file.name.rsplit('.', 1)
                    if len(name_parts) == 2:
                        # Has extension
                        child_file.name = f"{name_parts[0]} (1).{name_parts[1]}"
                    else:
                        # No extension
                        child_file.name = f"{child_file.name} (1)"
                
                # Restore the file (clear deleted_at)
                child_file.deleted_at = None
            
            self.db.commit()
            
            # Don't update parent folder size for restore (soft delete didn't change parent size)
            
            return {
                'uuid': folder_uuid,
                'restored': True
            }
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def get_by_owner(self, user_id: int) -> Dict[str, Any]:
        """Get all folders by owner."""
        try:
            folders = self.folder_repo.get_by_owner(user_id)
            return {
                'folders': [
                    {
                        'uuid': f.uuid,
                        'name': f.name,
                        'size': f.size,
                        'parent_id': f.parent_id,
                        'shared': f.shared,
                        'created_at': _fmt_utc8(f.created_at),
                        'updated_at': _fmt_utc8(f.updated_at)
                    }
                    for f in folders
                ]
            }
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def get_trash(self, user_id: int) -> Dict[str, Any]:
        """Get soft-deleted folders by owner."""
        try:
            folders = self.folder_repo.get_trash_by_owner(user_id)
            
            # Build path information for each folder
            folders_with_path = []
            for f in folders:
                # Get the folder path
                path = self._get_folder_path(f.uuid, user_id)
                
                folders_with_path.append({
                    'uuid': f.uuid,
                    'name': f.name,
                    'size': f.size,
                    'parent_id': f.parent_id,
                    'deleted_at': _fmt_utc8(f.deleted_at) if f.deleted_at else None,
                    'path': path
                })
            
            return {
                'folders': folders_with_path
            }
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def _get_folder_path(self, folder_uuid: str, user_id: int) -> str:
        """Get the full path of a folder as a string."""
        try:
            path_parts = []
            current_folder = self.db.execute(
                select(Folder).where(Folder.uuid == folder_uuid)
            ).scalar_one_or_none()
            
            _seen = set()
            while current_folder and current_folder.uuid not in _seen:
                _seen.add(current_folder.uuid)
                path_parts.append(current_folder.name)
                if current_folder.parent_id:
                    current_folder = self.db.execute(
                        select(Folder).where(Folder.uuid == current_folder.parent_id)
                    ).scalar_one_or_none()
                else:
                    break
            
            # Reverse to get the correct order (from root to current)
            path_parts.reverse()
            return ' / '.join(path_parts)
        except Exception:
            return 'Unknown'

    MAX_FOLDER_DEPTH = 64

    def _ancestor_chain(self, folder) -> list:
        """Return [folder, parent, ...] bounded; [] on cycle/missing."""
        chain = []
        seen = set()
        cur = folder
        while cur and len(chain) < self.MAX_FOLDER_DEPTH + 8:
            if cur.uuid in seen:
                break
            seen.add(cur.uuid)
            chain.append(cur)
            cur = self.folder_repo.get_by_uuid(cur.parent_id) if cur.parent_id else None
        return chain

    def resolve_or_create_path(self, user_id: int, base_folder_uuid: Optional[str], rel_path: str) -> Dict[str, Any]:
        """Resolve a relative path under base (or Home), creating missing folders."""
        try:
            from app.utils.pathing import sanitize_rel_path
            segments, err = sanitize_rel_path(rel_path)
            if err:
                return {'error': err, 'stateCode': HTTPStatus.BAD_REQUEST}

            current = base_folder_uuid
            if not current:
                home = self.folder_repo.get_home_folder(user_id)
                if not home:
                    return {'error': '找不到 Home 資料夾', 'stateCode': HTTPStatus.NOT_FOUND}
                current = home.uuid
            else:
                # Security (red-team F2): the mount base must belong to the
                # caller and be alive; otherwise a user could plant folders
                # inside another user's tree by supplying its UUID.
                base = self.folder_repo.get_by_uuid(current)
                if not base or base.owner_id != user_id or base.deleted_at is not None:
                    return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}
                chain = self._ancestor_chain(base)
                if len(chain) + len(segments) > self.MAX_FOLDER_DEPTH:
                    return {'error': '資料夾深度過深', 'stateCode': HTTPStatus.BAD_REQUEST}

            if not segments:
                return {'uuid': current, 'created': []}

            created = []
            for seg in segments:
                child = self.db.execute(
                    select(Folder).where(
                        Folder.owner_id == user_id,
                        Folder.parent_id == current,
                        Folder.name == seg,
                        Folder.deleted_at.is_(None),
                    )
                ).scalars().first()
                if child:
                    current = child.uuid
                    continue
                new_folder = Folder(uuid=str(uuid.uuid4()), owner_id=user_id, parent_id=current, name=seg, size=0)
                made = self.folder_repo.create_with_uuid_retry(new_folder)
                current = made.uuid
                created.append(seg)
            return {'uuid': current, 'created': created}
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def _ancestor_uuids(self, folder_uuid: str) -> set:
        """Full ancestor chain (inclusive), cycle-safe and UNBOUNDED in depth.

        DS2-4: the old 64-hop cut silently excluded deeper ancestors, so
        move's cycle check could be bypassed once depth > 64. Termination is
        guaranteed by the seen-set even on corrupted (cyclic) data.
        """
        chain = set()
        cur = self.folder_repo.get_by_uuid(folder_uuid)
        while cur and cur.uuid not in chain:
            chain.add(cur.uuid)
            cur = self.folder_repo.get_by_uuid(cur.parent_id) if cur.parent_id else None
        return chain

    def _subtree_height(self, folder_uuid: str, budget: int = 2000) -> int:
        """Max depth (in folders) of the subtree rooted at uuid; capped scan."""
        from collections import deque
        h = 0
        q = deque([(folder_uuid, 1)])
        seen = {folder_uuid}
        nodes = 0
        while q:
            u, d = q.popleft()
            h = max(h, d)
            kids = self.db.execute(
                select(Folder.uuid).where(Folder.parent_id == u)
            ).scalars().all()
            for k in kids:
                if k in seen:
                    continue
                seen.add(k)
                nodes += 1
                if nodes > budget:
                    return 10 ** 6  # effectively "too deep/wide" -> reject
                q.append((k, d + 1))
        return h

    def move_folders(self, user_id: int, folder_uuids: list[str], target_folder_uuid: str) -> Dict[str, Any]:
        """Move folders under target. Cycles/foreign are rejected per item; name collisions auto-renamed."""
        try:
            target = self.folder_repo.get_by_uuid(target_folder_uuid)
            if not target or target.owner_id != user_id or target.deleted_at:
                return {'error': '目標資料夾無效', 'stateCode': HTTPStatus.FORBIDDEN}

            target_depth = len(self._ancestor_uuids(target.uuid))
            moved, renamed, failed = [], {}, []
            rows = []
            for u in folder_uuids[:500]:
                folder = self.folder_repo.get_by_uuid(u)
                if not folder:
                    continue
                # DS2-3: keep the global depth invariant when re-parenting.
                if target_depth + self._subtree_height(folder.uuid) > self.MAX_FOLDER_DEPTH:
                    failed.append({"uuid": folder.uuid, "reason": "移動後資料夾深度超過上限"})
                    continue
                rows.append((len(self._ancestor_uuids(folder.uuid)), folder))
            rows.sort(key=lambda pair: pair[0])  # shallowest first

            for _, folder in rows:
                if folder.owner_id != user_id or folder.is_system:
                    failed.append({'uuid': folder.uuid, 'name': folder.name, 'reason': '無權限或系統資料夾'})
                    continue
                if folder.uuid in self._ancestor_uuids(target_folder_uuid):
                    failed.append({'uuid': folder.uuid, 'name': folder.name, 'reason': '無法移動到自身或其子資料夾'})
                    continue
                if folder.parent_id == target_folder_uuid:
                    moved.append(folder.uuid)
                    continue

                old_parent = folder.parent_id
                siblings = {
                    f.name for f in self.db.execute(
                        select(Folder).where(
                            Folder.parent_id == target_folder_uuid,
                            Folder.deleted_at.is_(None),
                            Folder.uuid != folder.uuid,
                        )
                    ).scalars().all()
                }
                from app.utils.pathing import unique_name
                new_name = unique_name(folder.name, siblings)
                folder.parent_id = target_folder_uuid
                if new_name != folder.name:
                    renamed[folder.name] = new_name
                    folder.name = new_name
                self.folder_repo.update(folder)

                size = folder.size or 0
                if old_parent:
                    self._update_parent_folder_size(old_parent, -size)
                self._update_parent_folder_size(target_folder_uuid, size)
                moved.append(folder.uuid)

            return {'moved': moved, 'renamed': renamed, 'failed': failed, 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
