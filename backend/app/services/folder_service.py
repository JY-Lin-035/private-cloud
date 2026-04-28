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
    
    def _hard_delete_children(self, folder_uuid: str) -> int:
        """Recursively hard delete all children (folders and files) and their storage files.
        Returns total size of all deleted items."""
        from app.repositories.file_repository import FileRepository
        from app.models.file import File
        import os

        file_repo = FileRepository(self.db)
        total_size = 0

        # Get all child folders
        child_folders = self.db.execute(
            select(Folder).where(Folder.parent_id == folder_uuid)
        ).scalars().all()

        for child_folder in child_folders:
            total_size += self._hard_delete_children(child_folder.uuid)
            total_size += child_folder.size
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
            total_size += child_file.size
            self.file_repo.hard_delete(child_file.uuid)

        return total_size
    
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
                children_size = self._hard_delete_children(folder_uuid)
                total_size = folder_size + children_size
                self.folder_repo.hard_delete(folder_uuid)

                # Update account used size only on hard delete (folder + all children)
                account.used_size = max(0, account.used_size - total_size)
                self.account_repo.update(account)

                # Update parent folder size with total size (folder + all children)
                if folder.parent_id:
                    self._update_parent_folder_size(folder.parent_id, -total_size)
            else:
                # Soft delete: recursively mark all children as deleted
                self._soft_delete_children(folder_uuid)
                self.folder_repo.soft_delete(folder_uuid)

                # Update parent folder size (for soft delete, only folder size)
                if folder.parent_id:
                    self._update_parent_folder_size(folder.parent_id, -folder_size)

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
            
            # Restore folder
            restored = self.folder_repo.restore(folder_uuid)
            
            # Restore all children
            from app.repositories.file_repository import FileRepository
            file_repo = FileRepository(self.db)
            
            child_folders = self.db.execute(
                select(Folder).where(Folder.parent_id == folder_uuid)
            ).scalars().all()
            
            for child_folder in child_folders:
                self.restore(user_id, child_folder.uuid)
            
            child_files = self.db.execute(
                select(File).where(File.parent_folder_id == folder_uuid)
            ).scalars().all()
            
            for child_file in child_files:
                file_repo.restore(child_file.uuid)
            
            # Update parent folder size
            if folder.parent_id:
                self._update_parent_folder_size(folder.parent_id, folder.size)
            
            return {
                'uuid': folder_uuid,
                'restored': restored
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
            return {
                'folders': [
                    {
                        'uuid': f.uuid,
                        'name': f.name,
                        'size': f.size,
                        'parent_id': f.parent_id,
                        'deleted_at': f.deleted_at.strftime('%Y-%m-%d %H:%M:%S') if f.deleted_at else None
                    }
                    for f in folders
                ]
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
