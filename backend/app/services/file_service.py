import uuid
import os
import mimetypes
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder
from app.repositories.account_repository import AccountRepository
from app.repositories.file_repository import FileRepository
from app.repositories.folder_repository import FolderRepository
from app.services.folder_service import FolderService
from app.constants import StorageLimits, HTTPStatus
from app.config import settings


class FileService:
    def __init__(self, db: Session):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.file_repo = FileRepository(db)
        self.folder_repo = FolderRepository(db)
        self.folder_service = FolderService(db)
        self.storage_base_path = settings.STORAGE_BASE_PATH
    
    def _get_mime_type(self, filename: str) -> str:
        """Get MIME type for a file."""
        mime_type, _ = mimetypes.guess_type(filename)
        return mime_type or 'application/octet-stream'
    
    def get_storage(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get storage usage information."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            total_storage = account.total_file_size or StorageLimits.DEFAULT_TOTAL_FILE_SIZE
            return {
                'used_storage': account.used_size,
                'signal_storage': account.signal_file_size,
                'total_storage': total_storage
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def get_file_list(self, user_id: int, parent_folder_uuid: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get list of files in a folder."""
        try:
            files = self.file_repo.get_by_folder(parent_folder_uuid) if parent_folder_uuid else []
            folders = self.folder_repo.get_by_parent(parent_folder_uuid) if parent_folder_uuid else self.folder_repo.get_by_owner(user_id)
            
            # Filter root-level folders (no parent)
            if not parent_folder_uuid:
                folders = [f for f in folders if f.parent_id is None]
            
            file_list = []
            
            for folder in folders:
                file_list.append({
                    'type': 'folder',
                    'uuid': folder.uuid,
                    'name': folder.name,
                    'size': folder.size,
                    'date': folder.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'shared': folder.shared
                })
            
            for file in files:
                file_list.append({
                    'type': 'file',
                    'uuid': file.uuid,
                    'name': file.name,
                    'size': file.size,
                    'date': file.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                    'mime_type': file.mime_type,
                    'shared': file.shared
                })
            
            return {'files': file_list, 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def upload_file(self, user_id: int, parent_folder_uuid: Optional[str], file, file_size: int) -> Optional[Dict[str, Any]]:
        """Upload a file."""
        try:
            account = self.account_repo.get_by_id(user_id)

            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}

            # Validate file size
            if file_size > account.signal_file_size:
                return {'error': '檔案大小超過限制', 'stateCode': HTTPStatus.FORBIDDEN}

            # Validate parent folder (if provided)
            if parent_folder_uuid:
                parent_folder = self.folder_repo.get_by_uuid(parent_folder_uuid)
                if not parent_folder or parent_folder.owner_id != user_id:
                    return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}

            # Validate filename
            filename = file.filename
            if '..' in filename or filename.startswith('.') or filename.startswith('/') or filename.startswith('\\'):
                return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}

            # Check if file with same name exists in same location
            from sqlalchemy import select
            existing_file = self.db.execute(
                select(File).where(
                    File.owner_id == user_id,
                    File.parent_folder_id == parent_folder_uuid,
                    File.name == filename,
                    File.deleted_at.is_(None)
                )
            ).scalar_one_or_none()

            # If exists, hard delete the old file
            old_file_size = 0
            if existing_file:
                old_file_size = existing_file.size
                # Delete old file from storage
                old_storage_path = os.path.join(self.storage_base_path, existing_file.uuid)
                if os.path.exists(old_storage_path):
                    os.remove(old_storage_path)
                # Hard delete from database
                self.file_repo.hard_delete(existing_file.uuid)

                # Update account used storage (remove old file size)
                account.used_size = max(0, account.used_size - old_file_size)
                self.account_repo.update(account)

                # Update parent folder size (remove old file size)
                if parent_folder_uuid:
                    self.folder_service._update_parent_folder_size(parent_folder_uuid, -old_file_size)

            # Generate UUID for file
            file_uuid = str(uuid.uuid4())

            # Create storage path
            storage_path = os.path.join(self.storage_base_path, file_uuid)

            # Ensure storage directory exists
            os.makedirs(self.storage_base_path, exist_ok=True)

            # Save file to storage
            with open(storage_path, 'wb') as f:
                f.write(file.file.read())

            # Create file record
            new_file = File(
                uuid=file_uuid,
                owner_id=user_id,
                parent_folder_id=parent_folder_uuid,
                name=filename,
                size=file_size,
                mime_type=self._get_mime_type(filename),
                storage_path=storage_path
            )

            created_file = self.file_repo.create_with_uuid_retry(new_file)

            # Update parent folder size
            if parent_folder_uuid:
                self.folder_service._update_parent_folder_size(parent_folder_uuid, file_size)

            # Update account used storage
            account.used_size += file_size
            self.account_repo.update(account)
            
            return {
                'uuid': created_file.uuid,
                'name': created_file.name,
                'size': created_file.size,
                'mime_type': created_file.mime_type,
                'created_at': created_file.created_at.strftime('%Y-%m-%d %H:%M:%S')
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def download(self, user_id: int, file_uuid: str) -> Optional[Dict[str, Any]]:
        """Download a file."""
        try:
            file = self.file_repo.get_by_uuid(file_uuid)

            if not file or file.owner_id != user_id or file.deleted_at:
                return {'error': 'NotFound', 'stateCode': HTTPStatus.NOT_FOUND}

            file_path = os.path.join(self.storage_base_path, file.uuid)
            if not os.path.exists(file_path):
                return {'error': 'File not found on disk', 'stateCode': HTTPStatus.NOT_FOUND}

            return {
                'real_path': file_path,
                'filename': file.name,
                'mime_type': file.mime_type,
                'stateCode': HTTPStatus.OK
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_ERROR}
    
    def delete(self, user_id: int, file_uuid: str, permanent: bool = False) -> Optional[Dict[str, Any]]:
        """Delete a file (soft or hard)."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            file = self.file_repo.get_by_uuid(file_uuid)
            
            if not file or file.owner_id != user_id:
                return {'error': 'NotFound', 'stateCode': HTTPStatus.NOT_FOUND}
            
            file_size = file.size

            if permanent:
                # Hard delete: remove from storage and database
                file_path = os.path.join(self.storage_base_path, file.uuid)
                if os.path.exists(file_path):
                    os.remove(file_path)
                self.file_repo.hard_delete(file_uuid)

                # Update account used storage only on hard delete
                account.used_size = max(0, account.used_size - file_size)
                self.account_repo.update(account)
            else:
                # Soft delete
                self.file_repo.soft_delete(file_uuid)

            # Update parent folder size only for hard delete (soft delete items still occupy space)
            if permanent and file.parent_folder_id:
                self.folder_service._update_parent_folder_size(file.parent_folder_id, -file_size)
            
            return {
                'uuid': file_uuid,
                'size': file_size,
                'permanent': permanent
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def restore(self, user_id: int, file_uuid: str) -> Optional[Dict[str, Any]]:
        """Restore a soft-deleted file."""
        try:
            file = self.db.execute(
                select(File).where(File.uuid == file_uuid)
            ).scalar_one_or_none()
            
            if not file or file.owner_id != user_id:
                return {'error': 'Error', 'stateCode': HTTPStatus.FORBIDDEN}
            
            if not file.deleted_at:
                return {'error': 'File not deleted', 'stateCode': HTTPStatus.BAD_REQUEST}
            
            # Check for name conflict with existing files in the same folder
            if file.parent_folder_id:
                existing_files = self.db.execute(
                    select(File).where(
                        File.parent_folder_id == file.parent_folder_id,
                        File.deleted_at.is_(None)
                    )
                ).scalars().all()
                existing_file_names = {f.name for f in existing_files}
                
                if file.name in existing_file_names:
                    # Rename file with (1) suffix
                    name_parts = file.name.rsplit('.', 1)
                    if len(name_parts) == 2:
                        # Has extension
                        file.name = f"{name_parts[0]} (1).{name_parts[1]}"
                    else:
                        # No extension
                        file.name = f"{file.name} (1)"
            
            # Restore the file (clear deleted_at)
            file.deleted_at = None
            
            self.db.commit()
            
            # Don't update parent folder size for restore (soft delete didn't change parent size)
            
            return {
                'uuid': file_uuid,
                'restored': True
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def get_by_owner(self, user_id: int) -> Dict[str, Any]:
        """Get all files by owner."""
        try:
            files = self.file_repo.get_by_owner(user_id)
            return {
                'files': [
                    {
                        'uuid': f.uuid,
                        'name': f.name,
                        'size': f.size,
                        'mime_type': f.mime_type,
                        'parent_folder_id': f.parent_folder_id,
                        'shared': f.shared,
                        'created_at': f.created_at.strftime('%Y-%m-%d %H:%M:%S'),
                        'updated_at': f.updated_at.strftime('%Y-%m-%d %H:%M:%S')
                    }
                    for f in files
                ]
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def get_trash(self, user_id: int) -> Dict[str, Any]:
        """Get soft-deleted files by owner."""
        try:
            files = self.file_repo.get_trash_by_owner(user_id)
            
            # Build path information for each file
            files_with_path = []
            for f in files:
                # Get the folder path for the file
                path = self._get_file_path(f.parent_folder_id, user_id) if f.parent_folder_id else 'Home'
                
                files_with_path.append({
                    'uuid': f.uuid,
                    'name': f.name,
                    'size': f.size,
                    'mime_type': f.mime_type,
                    'parent_folder_id': f.parent_folder_id,
                    'deleted_at': f.deleted_at.strftime('%Y-%m-%d %H:%M:%S') if f.deleted_at else None,
                    'path': path
                })
            
            return {
                'files': files_with_path
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def _get_file_path(self, folder_uuid: str, user_id: int) -> str:
        """Get the full path of a folder as a string."""
        try:
            from app.models.folder import Folder
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

    def recalculate_used_storage(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Recalculate used storage from actual non-deleted files."""
        try:
            account = self.account_repo.get_by_id(user_id)

            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}

            # Get all non-deleted files for the user
            from sqlalchemy import select
            files = self.db.execute(
                select(File).where(
                    File.owner_id == user_id,
                    File.deleted_at.is_(None)
                )
            ).scalars().all()

            # Sum up all file sizes
            total_used = sum(f.size for f in files)

            # Update account used_size
            account.used_size = total_used
            self.account_repo.update(account)

            return {
                'used_storage': total_used,
                'stateCode': HTTPStatus.OK
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
