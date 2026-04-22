import os
import base64
import re
from datetime import datetime
from typing import Optional, Dict, Any
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.account import Account
from app.repositories.account_repository import AccountRepository
from app.config import settings
from app.utils.logger_sample import log_info, log_error



class FolderService:
    def __init__(self, db: Session, storage_base_path: str = "storage/app/private"):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.storage_base_path = storage_base_path
    
    def _validate_path(self, user_id: int, dir: str) -> Optional[Path]:
        """Validate path to prevent directory traversal attacks."""
        try:
            # Decode base64 path (match Laravel logic: replace characters first, then decode)
            # Fallback: if not valid base64, treat as plain text with '-' as path separator
            if dir:
                try:
                    # Replace URL-safe characters (match Laravel strtr)
                    dir = dir.replace('-', '+').replace('_', '/')
                    # Add padding for URL-safe base64
                    padding = 4 - len(dir) % 4
                    if padding != 4:
                        dir += '=' * padding
                    # Decode base64
                    dir = base64.b64decode(dir).decode('utf-8')
                    # Replace remaining dashes with slashes (match Laravel str_replace)
                    dir = dir.replace('-', '/')
                except Exception:
                    # Not valid base64, treat as plain text (replace '-' with '/')
                    dir = dir.replace('-', '/')
            
            # Build full path
            user_path = Path(self.storage_base_path) / "users" / str(user_id)
            
            full_path = user_path / dir
            
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
            
            return real_path
        except Exception:
            return None
    
    def _validate_folder_name(self, name: str) -> bool:
        """Validate folder name (alphanumeric and Chinese characters only)."""
        return bool(re.match(r'^[A-Za-z0-9\u4e00-\u9fa5\s\-_\.]{1,30}$', name))
    
    def _calculate_folder_size(self, folder_path: Path) -> int:
        """Calculate total size of a folder recursively."""
        total_size = 0
        for item in folder_path.rglob('*'):
            if item.is_file():
                total_size += item.stat().st_size
        return total_size
    
    def create(self, user_id: int, dir: str, new_name: str) -> Optional[Dict[str, Any]]:
        """Create a new folder."""
        try:
            # Validate folder name
            if not self._validate_folder_name(new_name):
                return {'error': 'Error', 'stateCode': 403}
            
            # Validate path
            dir_path = self._validate_path(user_id, dir)
            
            if not dir_path or not dir_path.exists():
                return {'error': 'Error', 'stateCode': 403}
            
            # Check if folder already exists
            new_folder_path = dir_path / new_name
            if new_folder_path.exists():
                return {'error': 'Error', 'stateCode': 403}
            
            # Create folder
            new_folder_path.mkdir()
            
            # Match Laravel date format: Y-m-d H:i:s (local timezone)
            date_str = datetime.fromtimestamp(new_folder_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            return date_str
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def rename(self, user_id: int, dir: str, origin_name: str, new_name: str) -> Optional[Dict[str, Any]]:
        """Rename a folder."""
        try:
            # Validate folder names
            if not self._validate_folder_name(origin_name) or not self._validate_folder_name(new_name):
                return {'error': 'Error', 'stateCode': 403}
            
            # Validate path
            dir_path = self._validate_path(user_id, dir)
            
            if not dir_path or not dir_path.exists():
                return {'error': 'Error', 'stateCode': 403}
            
            # Get origin and new folder paths
            origin_folder_path = dir_path / origin_name
            new_folder_path = dir_path / new_name
            
            if not origin_folder_path.exists() or not origin_folder_path.is_dir():
                return {'error': 'Error', 'stateCode': 403}
            
            if new_folder_path.exists():
                return {'error': 'Error', 'stateCode': 403}
            
            # Rename folder
            origin_folder_path.rename(new_folder_path)
            
            return {'msg': 'success', 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def delete(self, user_id: int, dir: str, folder_name: str) -> Optional[Dict[str, Any]]:
        """Delete a folder recursively."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            # Validate path
            dir_path = self._validate_path(user_id, dir)
            
            if not dir_path or not dir_path.exists():
                return {'error': 'Error', 'stateCode': 403}
            
            # Get folder path
            folder_path = dir_path / folder_name
            
            if not folder_path.exists() or not folder_path.is_dir():
                return {'error': 'Error', 'stateCode': 403}
            
            # Calculate folder size before deletion
            folder_size = self._calculate_folder_size(folder_path)
            
            # Delete folder recursively
            for item in folder_path.rglob('*'):
                if item.is_file():
                    item.unlink()
                elif item.is_dir():
                    item.rmdir()
            folder_path.rmdir()
            
            # Update used storage
            account.used_size = max(0, account.used_size - folder_size)
            self.account_repo.update(account)
            
            return {'size': folder_size}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
