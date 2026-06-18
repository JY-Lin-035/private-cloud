import os
import json
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List
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
        """Get all shared items for a user. Filters out expired links and clears them from DB."""
        try:
            now = datetime.utcnow()
            now_local = now + timedelta(hours=8)  # Taiwan time (UTC+8)
            
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
                # Check if expired - if so, clear the share link from DB
                if folder.limited_date and now_local > folder.limited_date:
                    self.logger.info(f"Clearing expired share link for folder {folder.uuid}")
                    folder.shared = None
                    folder.limited_date = None
                    self.db.commit()
                    continue
                
                date_str = datetime.fromtimestamp(folder.updated_at.timestamp(), tz=timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                # Get folder path
                path = self.folder_repo.get_folder_path(folder.uuid)
                path_str = ' / '.join([p['name'] for p in path])
                limited_date_str = folder.limited_date.strftime('%Y-%m-%d %H:%M:%S') if folder.limited_date else None
                share_list.append({
                    'name': folder.name,
                    'path': path_str,
                    'link': folder.shared,
                    'uuid': folder.uuid,
                    'date': date_str,
                    'type': 'folder',
                    'limited_date': limited_date_str,
                    'available_user': folder.available_user
                })
            
            for file in files:
                # Check if file is expired - if so, clear the share link from DB
                if file.limited_date and now_local > file.limited_date:
                    self.logger.info(f"Clearing expired share link for file {file.uuid}")
                    file.shared = None
                    file.limited_date = None
                    self.db.commit()
                    continue
                
                date_str = datetime.fromtimestamp(file.updated_at.timestamp(), tz=timezone.utc).astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
                # Get file parent folder path
                if file.parent_folder_id:
                    path = self.folder_repo.get_folder_path(file.parent_folder_id)
                    path_str = ' / '.join([p['name'] for p in path]) + ' / ' + file.name
                else:
                    path_str = file.name
                limited_date_str = file.limited_date.strftime('%Y-%m-%d %H:%M:%S') if file.limited_date else None
                share_list.append({
                    'name': file.name,
                    'path': path_str,
                    'link': file.shared,
                    'uuid': file.uuid,
                    'date': date_str,
                    'type': 'file',
                    'limited_date': limited_date_str,
                    'available_user': file.available_user
                })
            
            return {'list': share_list, 'stateCode': HTTPStatus.OK}
        except Exception as e:
            self.logger.error(f"Error getting share list: {str(e)}")
            return {'error': str(e), 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def create_link(self, user_id: int, item_uuid: str, item_type: str, limited_date: Optional[datetime] = None, available_user: Optional[List[int]] = None) -> Optional[Dict[str, Any]]:
        """Create a share link for a folder or file. Always updates limited_date and available_user."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            # Convert available_user list to JSON string
            available_user_json = json.dumps(available_user) if available_user else None
            
            self.logger.info(f"create_link called: item_uuid={item_uuid}, item_type={item_type}, limited_date={limited_date}, available_user={available_user}")
            
            if item_type == 'folder':
                item = self.folder_repo.get_by_uuid(item_uuid)
                if not item or item.owner_id != user_id:
                    return {'error': '找不到資料夾', 'stateCode': HTTPStatus.NOT_FOUND}
                
                if not item.shared:
                    # Generate share hash only if not already shared
                    share_hash = self._generate_share_hash()
                    item.shared = share_hash
                
                # Always update limited_date and available_user
                item.limited_date = limited_date
                item.available_user = available_user_json
                self.folder_repo.update(item)
                
                self.logger.info(f"Folder share updated: uuid={item.uuid}, shared={item.shared}, limited_date={item.limited_date}")
                
                return {'url': item.shared, 'stateCode': HTTPStatus.OK}
            
            elif item_type == 'file':
                item = self.file_repo.get_by_uuid(item_uuid)
                if not item or item.owner_id != user_id:
                    return {'error': '找不到檔案', 'stateCode': HTTPStatus.NOT_FOUND}
                
                if not item.shared:
                    # Generate share hash only if not already shared
                    share_hash = self._generate_share_hash()
                    item.shared = share_hash
                
                # Always update limited_date and available_user
                item.limited_date = limited_date
                item.available_user = available_user_json
                self.file_repo.update(item)
                
                self.logger.info(f"File share updated: uuid={item.uuid}, shared={item.shared}, limited_date={item.limited_date}")
                
                return {'url': item.shared, 'stateCode': HTTPStatus.OK}
            
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
    
    def _check_share_access(self, item, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Check if a shared item is accessible. Returns error dict if not, None if OK."""
        # Check limited_date (expiration)
        if item.limited_date:
            now = datetime.utcnow()
            # limited_date is stored in local time (Taipei, UTC+8), so we need to compare with local time
            now_local = now + timedelta(hours=8)
            if now_local > item.limited_date:
                self.logger.warning(f"Share link expired for item {item.uuid}, limited_date: {item.limited_date}, now_local: {now_local}")
                return {'error': '分享連結已過期', 'stateCode': HTTPStatus.FORBIDDEN}
        
        # Check available_user (allowed user list)
        if item.available_user and user_id is not None:
            try:
                allowed_users = json.loads(item.available_user)
                if allowed_users and user_id not in allowed_users:
                    self.logger.warning(f"User {user_id} not in available_user list for item {item.uuid}")
                    return {'error': '您沒有權限存取此分享連結', 'stateCode': HTTPStatus.FORBIDDEN}
            except (json.JSONDecodeError, TypeError):
                self.logger.error(f"Failed to parse available_user for item {item.uuid}: {item.available_user}")
        
        return None
    
    def download(self, share_hash: str, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Download a file via share link."""
        try:
            # Try to find file by share hash
            file = self.db.execute(
                select(File).where(File.shared == share_hash)
            ).scalar_one_or_none()
            
            if file:
                # Check access permissions
                access_error = self._check_share_access(file, user_id)
                if access_error:
                    return access_error
                
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
                # Check access permissions
                access_error = self._check_share_access(folder)
                if access_error:
                    return access_error
                
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
