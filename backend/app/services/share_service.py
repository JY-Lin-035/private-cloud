import os
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from secrets import token_hex
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models.account import Account
from app.models.folder import Folder
from app.models.file import File
from app.repositories.account_repository import AccountRepository
from app.repositories.folder_repository import FolderRepository
from app.repositories.file_repository import FileRepository
from app.config import settings
from app.utils import logger as log
from app.constants import HTTPStatus


class ShareService:
    def __init__(self, db: Session):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.folder_repo = FolderRepository(db)
        self.file_repo = FileRepository(db)
        self.storage_base_path = settings.STORAGE_BASE_PATH
        self.logger = log.get_logger("share_service.log")
    
    def get_list(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get all shared items for a user."""
        try:
            # Get shared folders
            folders = self.db.execute(
                select(Folder).where(
                    Folder.owner_id == user_id,
                    Folder.shared.isnot(None)
                )
            ).scalars().all()
            
            # Get shared files
            files = self.db.execute(
                select(File).where(
                    File.owner_id == user_id,
                    File.shared.isnot(None)
                )
            ).scalars().all()
            
            share_list = []
            
            for folder in folders:
                date_str = datetime.fromtimestamp(folder.updated_at.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
                # Get folder path
                path = self.folder_repo.get_folder_path(folder.uuid)
                path_str = ' / '.join([p['name'] for p in path])
                share_list.append({
                    'name': folder.name,
                    'path': path_str,
                    'link': folder.shared,
                    'uuid': folder.uuid,
                    'date': date_str,
                    'type': 'folder'
                })
            
            for file in files:
                date_str = datetime.fromtimestamp(file.updated_at.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
                # Get file parent folder path
                if file.parent_folder_id:
                    path = self.folder_repo.get_folder_path(file.parent_folder_id)
                    path_str = ' / '.join([p['name'] for p in path]) + ' / ' + file.name
                else:
                    path_str = file.name
                share_list.append({
                    'name': file.name,
                    'path': path_str,
                    'link': file.shared,
                    'uuid': file.uuid,
                    'date': date_str,
                    'type': 'file'
                })
            
            return {'list': share_list, 'stateCode': HTTPStatus.OK}
        except Exception as e:
            self.logger.error(f"Error getting share list: {str(e)}")
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def create_link(self, user_id: int, item_uuid: str, item_type: str) -> Optional[Dict[str, Any]]:
        """Create a share link for a folder or file."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            if item_type == 'folder':
                item = self.folder_repo.get_by_uuid(item_uuid)
                if not item or item.owner_id != user_id:
                    return {'error': '找不到資料夾', 'stateCode': HTTPStatus.NOT_FOUND}
                
                if item.shared:
                    return {'url': item.shared, 'stateCode': 200}
                
                # Generate share hash
                share_hash = self._generate_share_hash()
                item.shared = share_hash
                self.folder_repo.update(item)
                
                return {'url': share_hash, 'stateCode': HTTPStatus.OK}
            
            elif item_type == 'file':
                item = self.file_repo.get_by_uuid(item_uuid)
                if not item or item.owner_id != user_id:
                    return {'error': '找不到檔案', 'stateCode': HTTPStatus.NOT_FOUND}
                
                if item.shared:
                    return {'url': item.shared, 'stateCode': 200}
                
                # Generate share hash
                share_hash = self._generate_share_hash()
                item.shared = share_hash
                self.file_repo.update(item)
                
                return {'url': share_hash, 'stateCode': HTTPStatus.OK}
            
            else:
                return {'error': '無效的項目類型', 'stateCode': HTTPStatus.BAD_REQUEST}
                
        except Exception as e:
            self.logger.error(f"Error creating share link: {str(e)}")
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def delete_link(self, user_id: int, item_uuid: str, item_type: str) -> Optional[Dict[str, Any]]:
        """Delete a share link."""
        try:
            # Trim parameters to handle URL encoding issues
            item_uuid = item_uuid.strip()
            item_type = item_type.strip()

            account = self.account_repo.get_by_id(user_id)

            if not account:
                self.logger.warning(f"User {user_id} not found")
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}

            if item_type == 'folder':
                item = self.folder_repo.get_by_uuid(item_uuid)
                if not item or item.owner_id != user_id:
                    return {'error': '找不到資料夾', 'stateCode': HTTPStatus.NOT_FOUND}

                item.shared = None
                self.folder_repo.update(item)

            elif item_type == 'file':
                item = self.file_repo.get_by_uuid(item_uuid)
                if not item or item.owner_id != user_id:
                    return {'error': '找不到檔案', 'stateCode': HTTPStatus.NOT_FOUND}

                item.shared = None
                self.file_repo.update(item)

            else:
                return {'error': '無效的項目類型', 'stateCode': HTTPStatus.BAD_REQUEST}

            return {'msg': 'success', 'stateCode': HTTPStatus.OK}
        except Exception as e:
            self.logger.error(f"Error deleting share link: {str(e)}")
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def download(self, share_hash: str) -> Optional[Dict[str, Any]]:
        """Download a file via share link."""
        try:
            # Try to find file by share hash
            file = self.db.execute(
                select(File).where(File.shared == share_hash)
            ).scalar_one_or_none()
            
            if file:
                file_path = Path(os.path.join(self.storage_base_path, file.uuid))
                if not file_path.exists() or not file_path.is_file():
                    self.logger.warning(f"File not found: {file_path}")
                    return {'error': '檔案不存在', 'stateCode': HTTPStatus.NOT_FOUND}

                self.logger.info(f"File found: {file_path} filename: {file.name}")
                return {
                    'real_path': str(file_path),
                    'filename': file.name,
                    'mime_type': file.mime_type,
                    'stateCode': HTTPStatus.OK
                }
            
            # Try to find folder by share hash (folder download not supported yet)
            folder = self.db.execute(
                select(Folder).where(Folder.shared == share_hash)
            ).scalar_one_or_none()
            
            if folder:
                return {'error': '資料夾分享不支援下載', 'stateCode': HTTPStatus.BAD_REQUEST}
            
            self.logger.warning(f"Share link not found: {share_hash}")
            return {'error': '分享連結不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
        except Exception as e:
            self.logger.error(f"Error downloading file: {str(e)}")
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def _generate_share_hash(self) -> str:
        """Generate a unique share hash."""
        for attempt in range(10):
            hash_value = hashlib.sha256(token_hex(16).encode()).hexdigest()[:32]
            
            # Check if hash already exists
            existing_file = self.db.execute(
                select(File).where(File.shared == hash_value)
            ).scalar_one_or_none()
            
            existing_folder = self.db.execute(
                select(Folder).where(Folder.shared == hash_value)
            ).scalar_one_or_none()
            
            if not existing_file and not existing_folder:
                return hash_value
        
        raise Exception("Failed to generate unique share hash")
