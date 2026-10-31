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
from app.utils.security import hash_password, verify_password
from app.utils.share_ticket import issue_ticket, verify_ticket
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
                    'available_user': folder.available_user,
                    'has_password': bool(folder.share_password)
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
                    'available_user': file.available_user,
                    'has_password': bool(file.share_password)
                })
            
            return {'list': share_list, 'stateCode': HTTPStatus.OK}
        except Exception as e:
            self.logger.error(f"Error getting share list: {str(e)}")
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def create_link(self, user_id: int, item_uuid: str, item_type: str, limited_date: Optional[datetime] = None, available_user: Optional[List[int]] = None, password: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Create a share link for a folder or file. Always updates limited_date and available_user.

        password semantics: None = keep existing, "" = clear, text = set (argon2 hash).
        """
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            # Convert available_user list to JSON string
            available_user_json = json.dumps(available_user) if available_user else None
            
            self.logger.info(f"create_link called: item_uuid={item_uuid}, item_type={item_type}, limited_date={limited_date}, available_user={available_user}, password_changed={password is not None}")
            
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
                if password is not None:
                    item.share_password = hash_password(password) if password else None
                self.folder_repo.update(item)
                
                self.logger.info(f"Folder share updated: uuid={item.uuid}, limited_date={item.limited_date}")
                
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
                if password is not None:
                    item.share_password = hash_password(password) if password else None
                self.file_repo.update(item)
                
                self.logger.info(f"File share updated: uuid={item.uuid}, limited_date={item.limited_date}")
                
                return {'url': item.shared, 'stateCode': HTTPStatus.OK}
            
            else:
                return {'error': '無效的項目類型', 'stateCode': HTTPStatus.BAD_REQUEST}
                
        except Exception as e:
            self.logger.error(f"Error creating share link: {str(e)}")
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
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
                item.share_password = None
                self.folder_repo.update(item)

            elif item_type == 'file':
                item = self.file_repo.get_by_uuid(item_uuid)
                if not item or item.owner_id != user_id:
                    return {'error': '找不到檔案', 'stateCode': HTTPStatus.NOT_FOUND}

                item.shared = None
                item.share_password = None
                self.file_repo.update(item)

            else:
                return {'error': '無效的項目類型', 'stateCode': HTTPStatus.BAD_REQUEST}

            return {'msg': 'success', 'stateCode': HTTPStatus.OK}
        except Exception as e:
            self.logger.error(f"Error deleting share link: {str(e)}")
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def _check_share_access(self, item, user_id: Optional[int] = None) -> Optional[Dict[str, Any]]:
        """Check if a shared item is accessible. Returns error dict if not, None if OK."""
        # Trashed items are NOT accessible via share links (defence-in-depth:
        # share hash is not cleared when a parent folder is soft-deleted, and
        # historical rows may predate share-clearing). Restoring the item
        # re-enables the link again, which is the intended UX.
        if getattr(item, "deleted_at", None) is not None:
            return {'error': '分享的項目不存在或已被移除', 'stateCode': HTTPStatus.NOT_FOUND}

        # Check available_user whitelist: an item restricted to specific users
        # must NEVER be served to anonymous callers (user_id None) either —
        # public endpoints do not pass a user_id, so a set whitelist is denied.
        if item.available_user:
            try:
                allowed_users = json.loads(item.available_user)
            except (json.JSONDecodeError, TypeError):
                allowed_users = []
            if allowed_users and user_id not in allowed_users:
                return {'error': '您沒有權限存取此分享連結', 'stateCode': HTTPStatus.FORBIDDEN}

        # Check limited_date (expiration; stored in local Taipei time UTC+8)
        if item.limited_date:
            now = datetime.utcnow()
            now_local = now + timedelta(hours=8)
            if now_local > item.limited_date:
                self.logger.warning(f"Share link expired for item {item.uuid}")
                return {'error': '分享連結已過期', 'stateCode': HTTPStatus.FORBIDDEN}

        return None
    
    def get_share_status(self, share_hash: str) -> Optional[Dict[str, Any]]:
        """Public metadata about a share link: existence, password and expiry state."""
        try:
            item = self.db.execute(
                select(File).where(File.shared == share_hash, File.deleted_at.is_(None))
            ).scalar_one_or_none()
            item_type = 'file'
            if not item:
                item = self.db.execute(
                    select(Folder).where(Folder.shared == share_hash, Folder.deleted_at.is_(None))
                ).scalar_one_or_none()
                item_type = 'folder'
            if not item:
                return {'exists': False, 'type': None, 'password_required': False, 'expired': False,
                        'stateCode': HTTPStatus.OK}
            expired = False
            if item.limited_date:
                now_local = datetime.utcnow() + timedelta(hours=8)
                expired = now_local > item.limited_date
            return {'exists': True, 'type': item_type, 'password_required': bool(item.share_password),
                    'expired': expired, 'stateCode': HTTPStatus.OK}
        except Exception as e:
            self.logger.error(f"Error getting share status: {str(e)}")
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def verify_share_password(self, share_hash: str, password: str) -> Optional[Dict[str, Any]]:
        """Validate the share password; on success issue a short-lived ticket."""
        try:
            item = self.db.execute(
                select(File).where(File.shared == share_hash)
            ).scalar_one_or_none()
            if not item:
                item = self.db.execute(
                    select(Folder).where(Folder.shared == share_hash)
                ).scalar_one_or_none()
            if not item or not item.share_password:
                return {'error': '無效的分享連結', 'stateCode': HTTPStatus.NOT_FOUND}
            access_error = self._check_share_access(item)
            if access_error:
                return access_error
            if not verify_password(password, item.share_password):
                self.logger.info(f"Share password verify failed for link {share_hash[:6]}…")
                return {'error': '密碼錯誤', 'stateCode': HTTPStatus.FORBIDDEN}
            return {'ticket': issue_ticket(share_hash, (item.share_password or '')[:16]),
                    'expires_in': settings.SHARE_TICKET_TTL_SECONDS,
                    'stateCode': HTTPStatus.OK}
        except Exception as e:
            self.logger.error(f"Error verifying share password: {str(e)}")
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def download(self, share_hash: str, user_id: Optional[int] = None, ticket: Optional[str] = None) -> Optional[Dict[str, Any]]:
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
                
                if file.share_password and not verify_ticket(share_hash, ticket, (file.share_password or '')[:16]):
                    return {'error': '此分享需要密碼', 'stateCode': 428}
                
                file_path = Path(os.path.join(self.storage_base_path, file.uuid))
                if not file_path.exists() or not file_path.is_file():
                    self.logger.warning("Shared file payload missing")
                    return {'error': '檔案不存在', 'stateCode': HTTPStatus.NOT_FOUND}

                self.logger.info(f"Share file resolved for download: {file.uuid}")
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
                
                if folder.share_password and not verify_ticket(share_hash, ticket, (folder.share_password or '')[:16]):
                    return {'error': '此分享需要密碼', 'stateCode': 428}
                
                return {'error': '資料夾分享不支援下載', 'stateCode': HTTPStatus.BAD_REQUEST}
            
            self.logger.warning(f"Share link not found: {share_hash[:6]}…")
            return {'error': '分享連結不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
        except Exception as e:
            self.logger.error(f"Error downloading file: {str(e)}")
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
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

    def _resolve_shared_folder(self, share_hash: str, ticket: Optional[str]):
        """Resolve a public folder link; enforces expiry + password ticket."""
        folder = self.db.execute(
            select(Folder).where(Folder.shared == share_hash)
        ).scalar_one_or_none()
        if not folder or folder.deleted_at:
            return None, {'error': '分享連結不存在', 'stateCode': HTTPStatus.NOT_FOUND}
        access_error = self._check_share_access(folder)
        if access_error:
            return None, access_error
        if folder.share_password and not verify_ticket(share_hash, ticket, (folder.share_password or '')[:16]):
            return None, {'error': '此分享需要密碼', 'stateCode': 428}
        return folder, None

    @staticmethod
    def _split_public_path(sub: Optional[str]) -> Optional[List[str]]:
        """Split a browse sub-path into safe segments; None when invalid."""
        if not sub:
            return []
        segments = [s for s in sub.replace('\\', '/').split('/') if s not in ('', '.')]
        if any(s == '..' or len(s) > 255 for s in segments):
            return None
        return segments

    def _walk_shared(self, root: Folder, segments: List[str]):
        cur = root
        for seg in segments:
            child = self.db.execute(
                select(Folder).where(
                    Folder.parent_id == cur.uuid,
                    Folder.name == seg,
                    Folder.owner_id == root.owner_id,
                    Folder.deleted_at.is_(None),
                )
            ).scalars().first()
            if not child:
                return None
            cur = child
        return cur

    def browse(self, share_hash: str, sub: Optional[str], ticket: Optional[str]) -> Dict[str, Any]:
        """List one level of a shared folder tree (names/sizes only, no uuids)."""
        try:
            folder, err = self._resolve_shared_folder(share_hash, ticket)
            if err:
                return err
            segments = self._split_public_path(sub)
            if segments is None:
                return {'error': '非法的路徑', 'stateCode': HTTPStatus.BAD_REQUEST}
            cur = self._walk_shared(folder, segments)
            if not cur:
                return {'error': '找不到目錄', 'stateCode': HTTPStatus.NOT_FOUND}

            child_folders = self.db.execute(
                select(Folder).where(
                    Folder.parent_id == cur.uuid,
                    Folder.deleted_at.is_(None),
                ).order_by(Folder.name)
            ).scalars().all()
            child_files = self.db.execute(
                select(File).where(
                    File.parent_folder_id == cur.uuid,
                    File.deleted_at.is_(None),
                ).order_by(File.name)
            ).scalars().all()

            return {
                'name': cur.name,
                'folders': [{'name': f.name, 'size': f.size or 0} for f in child_folders],
                'files': [{'name': f.name, 'size': f.size or 0} for f in child_files],
                'stateCode': HTTPStatus.OK,
            }
        except Exception as e:
            self.logger.error(f"Error browsing share: {str(e)}")
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}

    def collect_shared_items(self, share_hash: str, paths: List[str], ticket: Optional[str]):
        """Resolve public relative paths inside a shared folder into (file_uuids, folder_uuids)."""
        folder, err = self._resolve_shared_folder(share_hash, ticket)
        if err:
            return None, None, None, err
        file_uuids, folder_uuids = [], []
        for p in paths[:1000]:
            segments = self._split_public_path(p)
            if segments is None or not segments:
                continue
            parent = self._walk_shared(folder, segments[:-1])
            if not parent:
                continue
            last = segments[-1]
            sub = self.db.execute(
                select(Folder).where(
                    Folder.parent_id == parent.uuid, Folder.name == last,
                    Folder.owner_id == folder.owner_id, Folder.deleted_at.is_(None))
            ).scalars().first()
            if sub:
                folder_uuids.append(sub.uuid)
                continue
            f = self.db.execute(
                select(File).where(
                    File.parent_folder_id == parent.uuid, File.name == last,
                    File.owner_id == folder.owner_id, File.deleted_at.is_(None))
            ).scalars().first()
            if f:
                file_uuids.append(f.uuid)
        if not file_uuids and not folder_uuids:
            return None, None, None, {'error': '找不到可下載的項目', 'stateCode': HTTPStatus.NOT_FOUND}
        return folder.owner_id, file_uuids, folder_uuids, None
