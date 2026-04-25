import os
import base64
import hashlib
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from secrets import token_hex
from sqlalchemy.orm import Session
from app.models.account import Account
from app.models.share_link import ShareLink
from app.repositories.account_repository import AccountRepository
from app.repositories.share_link_repository import ShareLinkRepository
from app.config import settings
from app.utils import logger as log


class ShareService:
    def __init__(self, db: Session, storage_base_path: str = "storage/app/private"):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.share_link_repo = ShareLinkRepository(db)
        self.storage_base_path = storage_base_path
        self.logger = log.get_logger("share_service.log")
    
    def _validate_path(self, user_id: int, dir: str, filename: str = None) -> Optional[Path]:
        """Validate path to prevent directory traversal attacks."""
        try:
            # Decode base64 path with fallback to plain text
            if dir:
                try:
                    # Add padding for URL-safe base64
                    padding = 4 - len(dir) % 4
                    if padding != 4:
                        dir += '=' * padding
                    dir = base64.b64decode(dir.replace('-', '+').replace('_', '/')).decode('utf-8').replace('-', '/')
                except Exception:
                    # Not valid base64, treat as plain text (replace '-' with '/')
                    dir = dir.replace('-', '/')
            
            # Build full path (match file_service pattern, no automatic /Home)
            user_path = Path(self.storage_base_path) / "users" / str(user_id)
            if dir:
                full_path = user_path / dir
            else:
                full_path = user_path / "Home"
            
            if filename:
                full_path = full_path / filename
            
            # Get real path and validate
            real_path = full_path.resolve()
            
            # Check if path is within user's Home directory
            try:
                real_path.relative_to(user_path.resolve())
            except ValueError:
                return None
            
            # Check for path traversal attempts
            if '..' in str(full_path) or str(full_path).startswith('/') or str(full_path).startswith('\\'):
                return None
            
            if filename and ('..' in filename or filename.startswith('.') or filename.startswith('/') or filename.startswith('\\')):
                return None
            
            return real_path
        except Exception:
            return None
    
    def get_list(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get all share links for a user."""
        try:
            share_links = self.share_link_repo.get_by_owner(user_id)
            
            share_list = []
            for link in share_links:
                # Match Laravel date format: Y-m-d H:i:s (local timezone)
                date_str = datetime.fromtimestamp(link.updated_at.timestamp()).strftime('%Y-%m-%d %H:%M:%S')
                share_list.append({
                    'name': link.file_name or '',
                    'path': link.path,
                    'link': link.link,
                    'date': date_str
                })
            
            return {'list': share_list, 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def create_link(self, user_id: int, dir: str, filename: str) -> Optional[Dict[str, Any]]:
        """Create a share link for a file."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            # Validate path
            file_path = self._validate_path(user_id, dir, filename)
            
            if not file_path or not file_path.exists() or not file_path.is_file():
                return {'error': 'Error', 'stateCode': 404}
            
            # Decode dir for storage (with padding)
            if dir:
                try:
                    # Add padding for URL-safe base64
                    padding = 4 - len(dir) % 4
                    if padding != 4:
                        dir += '=' * padding
                    dir_decoded = base64.b64decode(dir.replace('-', '+').replace('_', '/')).decode('utf-8').replace('-', '/')
                except Exception:
                    # Not valid base64, treat as plain text
                    dir_decoded = dir.replace('-', '/')
            else:
                dir_decoded = ''
            
            # Check if share link already exists
            existing_link = self.share_link_repo.get_by_owner_and_path(user_id, dir_decoded, filename)
            if existing_link:
                return {'url': existing_link.link, 'stateCode': 200}
            
            # Generate unique link
            link = hashlib.sha512(f"{dir_decoded}{filename}{token_hex(8)}".encode()).hexdigest()
            
            # Create share link
            share_link = ShareLink(
                path=dir_decoded,
                file_name=filename,
                link=link,
                owner_id=user_id
            )
            
            self.share_link_repo.create(share_link)
            
            return {'url': link, 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def delete_link(self, user_id: int, dir: str, filename: str, link: str = None) -> Optional[Dict[str, Any]]:
        """Delete a share link."""
        try:
            account = self.account_repo.get_by_id(user_id)

            if not account:
                self.logger.warning(f"User {user_id} not found")
                return {'error': '使用者不存在', 'stateCode': 404}

            if dir and filename:
                # Delete by path and filename (with padding)
                if dir:
                    try:
                        # Add padding for URL-safe base64
                        padding = 4 - len(dir) % 4
                        if padding != 4:
                            dir += '=' * padding
                        dir_decoded = base64.b64decode(dir.replace('-', '+').replace('_', '/')).decode('utf-8').replace('-', '/')
                    except Exception:
                        # Not valid base64, treat as plain text
                        dir_decoded = dir.replace('-', '/')
                else:
                    dir_decoded = ''

                success = self.share_link_repo.delete_by_owner_and_path(user_id, dir_decoded, filename)
            elif link:
                # Delete by link
                success = self.share_link_repo.delete_by_link(link)
            else:
                self.logger.warning(f"Invalid parameters for delete_link: user_id={user_id}, dir={dir}, filename={filename}, link={link}")
                return {'error': 'Error', 'stateCode': 404}

            if success:
                return {'msg': 'success', 'stateCode': 200}
            else:
                self.logger.warning(f"Failed to delete share link: user_id={user_id}, dir={dir}, filename={filename}, link={link}")
                return {'error': 'Error', 'stateCode': 404}
        except Exception as e:
            self.logger.error(f"Error deleting share link: {str(e)}")
            return {'error': str(e), 'stateCode': 500}
    
    def download(self, link: str) -> Optional[Dict[str, Any]]:
        """Download a file via share link."""
        try:
            share_link = self.share_link_repo.get_by_link(link)

            if not share_link:
                self.logger.warning(f"Share link not found: {link}")
                return {'error': 'Error', 'stateCode': 404}

            # Build file path (path already includes Home/)
            file_path = Path(self.storage_base_path) / "users" / str(share_link.owner_id) / share_link.path / share_link.file_name

            if not file_path.exists() or not file_path.is_file():
                self.logger.warning(f"File not found: {file_path}")
                return {'error': 'Error', 'stateCode': 404}

            self.logger.info(f"File found: {file_path} filename: {share_link.file_name}")
            return {
                'real_path': str(file_path),
                'filename': share_link.file_name,
                'stateCode': 200
            }
        except Exception as e:
            self.logger.error(f"Error downloading file: {str(e)}")
            return {'error': str(e), 'stateCode': 500}
