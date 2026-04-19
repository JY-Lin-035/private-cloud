import os
import base64
from datetime import datetime
from typing import Optional, Dict, Any, List
from pathlib import Path
from sqlalchemy.orm import Session
from app.models.account import Account
from app.repositories.account_repository import AccountRepository
from app.utils.file_utils import format_file_size
from app.config import settings
from app.utils.logger import log_info, log_error


class FileService:
    def __init__(self, db: Session, storage_base_path: str = "storage/app/private"):
        self.db = db
        self.account_repo = AccountRepository(db)
        self.storage_base_path = storage_base_path
    
    def _validate_path(self, user_id: int, dir: str, filename: str = None) -> Optional[Path]:
        """Validate path to prevent directory traversal attacks."""
        try:
            # Decode base64 path (match Laravel logic: decode first, then replace)
            # Fallback: if not valid base64, treat as plain text with '-' as path separator
            if dir:
                try:
                    # Add padding for URL-safe base64
                    padding = 4 - len(dir) % 4
                    if padding != 4:
                        dir += '=' * padding
                    dir = base64.b64decode(dir.replace('-', '+').replace('_', '/')).decode('utf-8')
                    dir = dir.replace('-', '/')
                except Exception:
                    # Not valid base64, treat as plain text (replace '-' with '/')
                    dir = dir.replace('-', '/')
            
            # Build full path
            user_path = Path(self.storage_base_path) / "users" / str(user_id)
            
            full_path = user_path / dir
            
            if filename:
                full_path = full_path / filename
            
            # Get real path and validate
            real_path = full_path.resolve()
            log_info("get_file_list - real_path: " + str(real_path))
            
            # Check if path is within user's Home directory
            try:
                real_path.relative_to(user_path.resolve())
            except ValueError:
                log_info("get_file_list - path traversal attempt", {"user_id": user_id, "path": str(full_path)})
                return None
            
            # Check for path traversal attempts
            if '..' in str(full_path) or str(full_path).startswith('/') or str(full_path).startswith('\\'):
                log_info("get_file_list - path traversal attempt", {"user_id": user_id, "path": str(full_path)})
                return None
            
            if filename and ('..' in filename or filename.startswith('.') or filename.startswith('/') or filename.startswith('\\')):
                log_info("get_file_list - filename traversal attempt", {"user_id": user_id, "filename": filename})
                return None
            
            return real_path
        except Exception as e:
            log_info("get_file_list - exception", {"user_id": user_id, "dir": dir, "filename": filename, "error": str(e)})
            return None
    
    def get_storage(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Get storage usage information."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            # Ensure totalStorage is never 0 to prevent frontend NaN
            total_storage = account.total_file_size or 10737418240
            return {
                'usedStorage': account.used_size,
                'signalStorage': account.signal_file_size,
                'totalStorage': total_storage
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def get_file_list(self, user_id: int, folder: str) -> Optional[Dict[str, Any]]:
        """Get list of files in a folder."""
        try:
            folder_path = self._validate_path(user_id, folder)
            log_info(f"get_file_list - folder_path: {folder_path}")

            if not folder_path:
                log_info("get_file_list - folder_path is None after validation")
                return {'error': 'Error', 'stateCode': 404}

            if not folder_path.exists():
                log_info(f"get_file_list - folder_path does not exist: {folder_path}")
                return {'error': 'Error', 'stateCode': 404}

            log_info(f"get_file_list - folder_path exists, is_dir: {folder_path.is_dir()}")

            file_list = []
            item_count = 0

            for item in folder_path.iterdir():
                item_count += 1
                log_info(f"get_file_list - found item: {item.name}, is_file: {item.is_file()}, is_dir: {item.is_dir()}")
                if item.is_file():
                    size, unit = format_file_size(item.stat().st_size)
                    size_str = f"{size} {unit}" if unit else str(size)
                    # Match Laravel date format: Y-m-d H:i:s (local timezone)
                    date_str = datetime.fromtimestamp(item.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    file_list.append({
                        'type': 'file',
                        'name': item.name,
                        'size': size_str,
                        'date': date_str
                    })
                elif item.is_dir():
                    date_str = datetime.fromtimestamp(item.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
                    file_list.append({
                        'type': 'folder',
                        'name': item.name,
                        'size': '-',
                        'date': date_str
                    })

            log_info(f"get_file_list - total items found: {item_count}, file_list length: {len(file_list)}")
            return {'file': file_list, 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def upload_file(self, user_id: int, dir: str, file, file_size: int) -> Optional[Dict[str, Any]]:
        """Upload a file."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            # Validate file size
            if file_size > account.signal_file_size:
                return {'error': '檔案大小超過限制', 'stateCode': 403}
            
            # Validate path (default to Home if dir is empty or 'Home')
            # Use base64 encoded 'Home' (SG9tZQ) to match normal flow
            if not dir or dir == "Home":
                dir_path = self._validate_path(user_id, "SG9tZQ")
            else:
                dir_path = self._validate_path(user_id, dir)
            
            if not dir_path or not dir_path.exists():
                return {'error': 'Error', 'stateCode': 403}
            
            # Validate filename
            filename = file.filename
            if '..' in filename or filename.startswith('.') or filename.startswith('/') or filename.startswith('\\'):
                return {'error': 'Error', 'stateCode': 403}
            
            # Check if file already exists with same size
            file_path = dir_path / filename
            if file_path.exists():
                if file_path.stat().st_size == file_size:
                    return {'message': 'success'}
            
            # Save file
            with open(file_path, 'wb') as f:
                f.write(file.file.read())
            
            # Update used storage
            account.used_size += file_size
            self.account_repo.update(account)
            
            return {'message': 'success'}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def download(self, user_id: int, dir: str, filename: str) -> Optional[Dict[str, Any]]:
        """Download a file."""
        try:
            file_path = self._validate_path(user_id, dir, filename)
            
            if not file_path or not file_path.exists() or not file_path.is_file():
                return {'error': 'NotFound', 'stateCode': 404}
            
            return {
                'real_path': str(file_path),
                'filename': filename,
                'stateCode': 200
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def delete(self, user_id: int, dir: str, filename: str) -> Optional[Dict[str, Any]]:
        """Delete a file."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            file_path = self._validate_path(user_id, dir, filename)
            
            if not file_path or not file_path.exists() or not file_path.is_file():
                return {'error': 'NotFound', 'stateCode': 404}
            
            # Get file size
            file_size = file_path.stat().st_size
            
            # Delete file
            file_path.unlink()
            
            # Update used storage
            account.used_size = max(0, account.used_size - file_size)
            self.account_repo.update(account)
            
            return {'size': file_size}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
