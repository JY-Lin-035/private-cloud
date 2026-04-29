import uuid
import re
import os
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.account import Account
from app.models.folder import Folder
from app.models.file import File
from app.repositories.account_repository import AccountRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.file_repository import FileRepository
from app.constants import FolderValidation, HTTPStatus
from app.config import settings


class FolderService:
    def __init__(self, db: Session):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.folder_repo = FolderRepository(db)
        self.file_repo = FileRepository(db)
        self.storage_base_path = settings.STORAGE_BASE_PATH
    
    def _validate_folder_name(self, name: str) -> bool:
        """Validate folder name (alphanumeric and Chinese characters only)."""
        pattern = f'^[A-Za-z0-9\u4e00-\u9fa5\\s\\-_\\.]{{{FolderValidation.MIN_LENGTH},{FolderValidation.MAX_LENGTH}}}$'
        return bool(re.match(pattern, name))
    
    def _update_parent_folder_size(self, folder_uuid: str, size_delta: int):
        """Recursively update parent folder sizes."""
        folder = self.folder_repo.get_by_uuid(folder_uuid)
        if not folder:
            return
        
        # Update current folder size
        folder.size = max(0, folder.size + size_delta)
        self.folder_repo.update(folder)
        
        # Recursively update parent
        if folder.parent_id:
            self._update_parent_folder_size(folder.parent_id, size_delta)
    
    def _soft_delete_children(self, folder_uuid: str):
        """Recursively soft delete all children (folders and files)."""
        from app.repositories.file_repository import FileRepository
        from app.models.file import File
        
        file_repo = FileRepository(self.db)
        
        # Get all child folders
        child_folders = self.folder_repo.get_by_parent(folder_uuid)
        for child_folder in child_folders:
            self._soft_delete_children(child_folder.uuid)
            self.folder_repo.soft_delete(child_folder.uuid)
        
        # Get all child files
        child_files = file_repo.get_by_folder(folder_uuid)
        for child_file in child_files:
            file_repo.soft_delete(child_file.uuid)
    
    def _hard_delete_children(self, folder_uuid: str) -> None:
        """Recursively hard delete all children (folders and files) and their storage files.
        Only responsible for deletion, not size calculation."""
        from app.repositories.file_repository import FileRepository
        from app.models.file import File
        import os

        file_repo = FileRepository(self.db)

        # Get all child folders
        child_folders = self.db.execute(
            select(Folder).where(Folder.parent_id == folder_uuid)
        ).scalars().all()

        for child_folder in child_folders:
            # Recursively delete children first
            self._hard_delete_children(child_folder.uuid)
            # Delete the folder itself
            self.folder_repo.hard_delete(child_folder.uuid)

        # Get all child files (including deleted ones)
        child_files = self.db.execute(
            select(File).where(File.parent_folder_id == folder_uuid)
        ).scalars().all()

        for child_file in child_files:
            # Delete actual file from storage
            file_path = os.path.join(self.storage_base_path, child_file.uuid)
            if os.path.exists(file_path):
                os.remove(file_path)
            # Delete file record from database
            self.file_repo.hard_delete(child_file.uuid)
    
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
            
            # Check for duplicate folder name in same parent directory
            existing_folder = self.db.execute(
                select(Folder).where(
                    Folder.owner_id == user_id,
                    Folder.parent_id == parent_folder_uuid,
                    Folder.name == name,
                    Folder.deleted_at.is_(None)
                )
            ).scalar_one_or_none()
            
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
                'created_at': created_folder.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
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
            
            # Update name
            folder.name = new_name
            self.folder_repo.update(folder)
            
            return {
                'uuid': folder.uuid,
                'name': folder.name,
                'updated_at': folder.updated_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
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

            return {
                'uuid': folder_uuid,
                'size': folder_size,
                'permanent': permanent
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
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
            
            # Recursive function to restore all children under folder_uuid
            def restore_all_children_recursive(parent_uuid: str):
                """Recursively restore all children (folders and files) under parent_uuid."""
                from app.models.file import File
                
                # Get all child folders
                child_folders = self.db.execute(
                    select(Folder).where(Folder.parent_id == parent_uuid)
                ).scalars().all()
                
                for child_folder in child_folders:
                    child_folder.deleted_at = None
                    # Recursively restore nested children
                    restore_all_children_recursive(child_folder.uuid)
                
                # Get all child files
                child_files = self.db.execute(
                    select(File).where(File.parent_folder_id == parent_uuid)
                ).scalars().all()
                
                for child_file in child_files:
                    child_file.deleted_at = None
            
            restore_all_children_recursive(folder_uuid)
            
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
                    from app.repositories.file_repository import FileRepository
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
                    return {'error': f'合併失敗: {str(e)}', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
            
            # No conflict, proceed with normal restore
            # Restore the folder (clear deleted_at)
            folder.deleted_at = None
            
            # Restore all children
            from app.repositories.file_repository import FileRepository
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
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
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
                        'created_at': f.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': f.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    for f in folders
                ]
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
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
                    'deleted_at': f.deleted_at.strftime('%Y-%m-%d %H:%M:%S') if f.deleted_at else None,
                    'path': path
                })
            
            return {
                'folders': folders_with_path
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def _get_folder_path(self, folder_uuid: str, user_id: int) -> str:
        """Get the full path of a folder as a string."""
        try:
            path_parts = []
            current_folder = self.db.execute(
                select(Folder).where(Folder.uuid == folder_uuid)
            ).scalar_one_or_none()
            
            while current_folder:
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
