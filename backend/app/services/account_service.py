from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from redis import Redis
import os
import json
from app.models.account import Account
from app.repositories.account_repository import AccountRepository
from app.utils.email_utils import format_email, mask_email
from app.utils.security import hash_password, verify_password, generate_session_token, hash_token, generate_verification_code, generate_signed_url, verify_signed_url
from app.config import settings


class AccountService:
    def __init__(self, db: Session, redis_client: Redis):
        self.db = db
        self.redis = redis_client
        self.account_repo = AccountRepository(db)
    
    def register(self, username: str, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Register a new account."""
        try:
            # Check if username or email already exists
            if self.account_repo.name_exists(username):
                return {'error': '此用戶名已被使用', 'stateCode': 409}
            
            formatted_email = format_email(email)
            if self.account_repo.email_exists(formatted_email):
                return {'error': '此電子信箱地址已被使用', 'stateCode': 409}
            
            # Create account
            account = Account(
                name=username,
                password=hash_password(password),
                email=formatted_email,
                signal_file_size=524288000,  # 500MB
                total_file_size=10737418240,  # 10GB
                used_size=0,
                identity=0,  # User
                enable=False,
                email_verified_at=None,
                delete_date=None,
                last_sign_in_date=None
            )
            
            self.account_repo.create(account)
            user_folder = os.path.join('storage', 'app', 'private', 'users', str(account.id), 'Home')
            os.makedirs(user_folder, exist_ok=True)
            
            # Generate verification data and store in Redis
            hash_value, signature, timestamp, secret_key = generate_signed_url(account.id, account.email)
            # Store in Redis: user_id|hash|timestamp|secret_key with expiration
            self.redis.setex(
                f"registerVerifyMail:{account.id}",
                settings.MAIL_VAL_EXPIRE_TIME * 60,
                f"{account.id}|{hash_value}|{timestamp}|{secret_key}"
            )
            
            return None
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def login(self, username: str, password: str, email_service=None) -> Optional[Dict[str, Any]]:
        """Login user and create session."""
        try:
            account = self.account_repo.get_by_name(username)
            
            if not account:
                return {'error': '使用者名稱不存在', 'stateCode': 404}
            
            if not verify_password(password, account.password):
                return {'error': '密碼錯誤!', 'stateCode': 401}
            
            if not account.email_verified_at:
                # Re-send verification email like Laravel does
                if email_service:
                    email_service.send_verification_email(account.id, account.email)
                return {'error': '信箱地址尚未驗證!', 'stateCode': 403}
            
            if not account.enable:
                return {'error': '目前該帳號位於小黑屋，如有疑慮請聯絡管理員', 'stateCode': 403}
            
            if account.delete_date:
                return {'error': '帳號已刪除，如有疑慮請聯絡管理員', 'stateCode': 403}
            
            # Generate session token
            session_token = generate_session_token(account.id)
            
            # Store session in Redis
            session_data = {
                'user_id': account.id,
                'username': account.name,
                'email': account.email,
                'identity': account.identity
            }
            self.redis.setex(
                f"session:{account.id}",
                settings.TOKEN_EXPIRE_TIME * 60,
                session_token
            )
            self.redis.setex(
                f"session_data:{account.id}",
                settings.TOKEN_EXPIRE_TIME * 60,
                json.dumps(session_data)
            )
            
            # Update last sign in date
            account.last_sign_in_date = datetime.utcnow()
            self.account_repo.update(account)
            
            return {
                'token': session_token,
                'email': mask_email(account.email),
                'stateCode': 200
            }
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def sign_out(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Sign out user by deleting session from Redis."""
        try:
            self.redis.delete(f"session:{user_id}")
            self.redis.delete(f"session_data:{user_id}")
            return None
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def modify_email(self, user_id: int, new_email: str, check_email: str, code: str) -> Optional[Dict[str, Any]]:
        """Modify user email with verification code."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            formatted_check_email = format_email(check_email)
            if formatted_check_email != account.email:
                return {'error': '目前電子信箱錯誤', 'stateCode': 403}
            
            # Verify code from Redis
            stored_code = self.redis.get(f"mailCode:{formatted_check_email}")
            if not stored_code or stored_code.decode() != code:
                return {'error': '驗證碼錯誤', 'stateCode': 403}
            
            # Delete code from Redis
            self.redis.delete(f"mailCode:{formatted_check_email}")
            
            # Update email
            formatted_new_email = format_email(new_email)
            account.email = formatted_new_email
            account.email_verified_at = datetime.utcnow()
            self.account_repo.update(account)
            
            return {'email': mask_email(formatted_new_email), 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def modify_password(self, user_id: int, current_password: str, new_password: str) -> Optional[Dict[str, Any]]:
        """Modify user password."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            if not verify_password(current_password, account.password):
                return {'error': '目前密碼錯誤', 'stateCode': 403}
            
            account.password = hash_password(new_password)
            self.account_repo.update(account)
            
            # Invalidate all sessions
            self.sign_out(user_id)
            
            return {'message': 'success', 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def get_code(self, email: str, mode: str) -> Optional[Dict[str, Any]]:
        """Generate and send verification code."""
        try:
            formatted_email = format_email(email)
            account = self.account_repo.get_by_email(formatted_email)
            
            if mode == 'pw' and not account:
                return {'error': '該信箱地址尚未註冊', 'stateCode': 404}
            
            if mode == 'mail' and account:
                return {'error': '該信箱地址已註冊', 'stateCode': 409}
            
            if mode not in ['pw', 'mail']:
                return {'error': 'Error', 'stateCode': 404}
            
            # Generate verification code
            code = generate_verification_code()
            
            # Store code in Redis with expiration
            self.redis.setex(
                f"{mode}Code:{formatted_email}",
                settings.RESET_PW_CODE_EXPIRE_TIME * 60,
                code
            )
            
            # Queue email (to be implemented in email service)
            
            return {'message': '請至信箱查看通知', 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def reset_password(self, email: str, code: str, new_password: str) -> Optional[Dict[str, Any]]:
        """Reset password with verification code."""
        try:
            formatted_email = format_email(email)
            account = self.account_repo.get_by_email(formatted_email)
            
            if not account:
                return {'error': '該信箱地址尚未註冊', 'stateCode': 404}
            
            # Verify code from Redis
            stored_code = self.redis.get(f"pwCode:{formatted_email}")
            if not stored_code or stored_code.decode() != code:
                return {'error': '驗證碼錯誤', 'stateCode': 403}
            
            # Delete code from Redis
            self.redis.delete(f"pwCode:{formatted_email}")
            
            # Update password
            account.password = hash_password(new_password)
            self.account_repo.update(account)
            
            # Invalidate all sessions
            self.sign_out(account.id)
            
            return {'message': 'success', 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
    
    def verify_email(self, user_id: int, hash: str, signature: str = None) -> Optional[Dict[str, Any]]:
        """Verify email with signed URL (Laravel style)."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': 404}
            
            # Verify using Redis
            if not verify_signed_url(user_id, hash, signature, self.redis):
                return {'error': '驗證連結無效或已過期', 'stateCode': 403}
            
            # Delete from Redis
            self.redis.delete(f"registerVerifyMail:{user_id}")
            
            # Update account
            account.email_verified_at = datetime.utcnow()
            account.enable = True
            self.account_repo.update(account)
            
            return {'message': 'Email verified successfully.', 'stateCode': 200}
        except Exception as e:
            return {'error': str(e), 'stateCode': 500}
