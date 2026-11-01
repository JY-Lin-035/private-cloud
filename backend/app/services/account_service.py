from typing import Optional, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from redis import Redis
import os
import json
import uuid as uuid_lib
from app.models.account import Account
from app.models.folder import Folder
from app.repositories.account_repository import AccountRepository
from app.repositories.folder_repository import FolderRepository
from app.utils.email_utils import format_email, mask_email
from app.utils.security import hash_password, verify_password, generate_session_token, hash_token, generate_verification_code, generate_signed_url, verify_signed_url
from app.config import settings
from app.constants import StorageLimits, Identity, HTTPStatus, AccountDefaults

# Constant Argon2 hash used to burn the same verification time on logins for
# nonexistent accounts as on wrong passwords, so response timing cannot be
# used to enumerate usernames. Computed once at import.
_TIMING_PLACEHOLDER_HASH = hash_password("not-a-real-password-timing-equalizer")


class AccountService:
    def __init__(self, db: Session, redis_client: Redis):
        self.db = db
        self.redis = redis_client
        self.account_repo = AccountRepository(db)
        self.folder_repo = FolderRepository(db)
    
    def register(self, username: str, email: str, password: str) -> Optional[Dict[str, Any]]:
        """Register a new account."""
        try:
            # Check if username or email already exists
            if self.account_repo.name_exists(username):
                return {'error': '此用戶名已被使用', 'stateCode': HTTPStatus.CONFLICT}
            
            formatted_email = format_email(email)
            if self.account_repo.email_exists(formatted_email):
                return {'error': '此電子信箱地址已被使用', 'stateCode': HTTPStatus.CONFLICT}
            
            # Create account
            account = Account(
                name=username,
                password=hash_password(password),
                email=formatted_email,
                signal_file_size=StorageLimits.DEFAULT_SIGNAL_FILE_SIZE,
                total_file_size=StorageLimits.DEFAULT_TOTAL_FILE_SIZE,
                used_size=AccountDefaults.USED_SIZE,
                identity=Identity.USER,
                enable=AccountDefaults.ENABLE,
                email_verified_at=None,
                delete_date=None,
                last_sign_in_date=None
            )
            
            self.account_repo.create(account)
            
            # Create Home folder for the user (database record only, no physical directory)
            home_folder = Folder(
                uuid=str(uuid_lib.uuid4()),
                owner_id=account.id,
                parent_id=None,
                name='Home',
                size=0,
                is_system=True  # Home folder cannot be deleted
            )
            self.folder_repo.create(home_folder)
            
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
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def login(self, username: str, password: str, email_service=None) -> Optional[Dict[str, Any]]:
        """Login user and create session."""
        try:
            account = self.account_repo.get_by_name(username)
            
            if not account:
                # Same Argon2 cost as the wrong-password path (timing oracle).
                verify_password(password, _TIMING_PLACEHOLDER_HASH)
                return {'error': '使用者名稱或密碼錯誤', 'stateCode': HTTPStatus.UNAUTHORIZED}
            
            if not verify_password(password, account.password):
                return {'error': '使用者名稱或密碼錯誤', 'stateCode': HTTPStatus.UNAUTHORIZED}
            
            if not account.email_verified_at:
                # Re-send verification email like Laravel does
                if email_service:
                    from app.services.feature_flag_service import FeatureFlagService
                    if FeatureFlagService(self.db).effective_enabled("enable_verification_email"):
                        # DS2: per-account resend cooldown (10 min) so the
                        # mailer cannot be farmed across IPs via logins.
                        try:
                            if self.redis.set(f"resendV:{account.id}", "1", nx=True, ex=600):
                                email_service.send_verification_email(account.id, account.email)
                        except Exception:
                            pass
                return {'error': '信箱地址尚未驗證!', 'stateCode': HTTPStatus.FORBIDDEN}
            
            if not account.enable:
                return {'error': '目前該帳號位於小黑屋，如有疑慮請聯絡管理員', 'stateCode': HTTPStatus.FORBIDDEN}
            
            if account.delete_date:
                return {'error': '帳號已刪除，如有疑慮請聯絡管理員', 'stateCode': HTTPStatus.FORBIDDEN}
            
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
                'stateCode': HTTPStatus.OK
            }
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def sign_out(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Sign out user by deleting session from Redis."""
        try:
            self.redis.delete(f"session:{user_id}")
            self.redis.delete(f"session_data:{user_id}")
            try:
                from app.services import collab_events
                collab_events.revoke_user(user_id, "session ended")
            except Exception:
                pass
            return None
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def modify_email(self, user_id: int, new_email: str, check_email: str, code: str) -> Optional[Dict[str, Any]]:
        """Modify user email with verification code.

        The code is issued for the *new* address by get_code(mode="mail"), so it
        must be read from `mailCode:{new_email}`. `check_email` is the current
        address and must match the account (proof of identity).
        """
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            formatted_check_email = format_email(check_email)
            if formatted_check_email != account.email:
                return {'error': '目前電子信箱錯誤', 'stateCode': HTTPStatus.FORBIDDEN}
            
            formatted_new_email = format_email(new_email)
            if formatted_new_email != account.email and self.account_repo.email_exists(formatted_new_email):
                return {'error': '此電子信箱地址已被使用', 'stateCode': HTTPStatus.CONFLICT}
            
            # Verify code issued for the NEW address
            stored_code = self.redis.get(f"mailCode:{formatted_new_email}")
            if not stored_code:
                return {'error': '驗證碼錯誤', 'stateCode': HTTPStatus.FORBIDDEN}
            stored_str = stored_code.decode() if isinstance(stored_code, bytes) else stored_code
            if stored_str != code:
                return {'error': '驗證碼錯誤', 'stateCode': HTTPStatus.FORBIDDEN}
            
            self.redis.delete(f"mailCode:{formatted_new_email}")
            
            account.email = formatted_new_email
            account.email_verified_at = datetime.utcnow()
            try:
                self.account_repo.update(account)
            except Exception:
                self.db.rollback()
                return {'error': '此電子信箱地址已被使用', 'stateCode': HTTPStatus.CONFLICT}
            
            return {'email': mask_email(formatted_new_email), 'stateCode': HTTPStatus.OK}
        except Exception:
            return {'error': '信箱變更失敗', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def modify_password(self, user_id: int, current_password: str, new_password: str) -> Optional[Dict[str, Any]]:
        """Modify user password."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            if not verify_password(current_password, account.password):
                return {'error': '目前密碼錯誤', 'stateCode': HTTPStatus.FORBIDDEN}
            
            account.password = hash_password(new_password)
            self.account_repo.update(account)
            
            # Invalidate all sessions
            self.sign_out(user_id)
            
            return {'message': 'success', 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def get_code(self, email: str, mode: str) -> Optional[Dict[str, Any]]:
        """Generate a verification code.

        Responses are intentionally uniform for existent and non-existent
        addresses (prevents account enumeration). The plaintext code is returned
        ONLY so the API layer can e-mail it; it is never placed in the HTTP body.
        """
        try:
            formatted_email = format_email(email)
            account = self.account_repo.get_by_email(formatted_email)
            
            if mode not in ('pw', 'mail'):
                return {'message': '若符合條件，通知已寄出', 'stateCode': HTTPStatus.OK}
            
            if mode == 'pw':
                generic = {'message': '若此信箱已註冊，將寄出重設通知', 'stateCode': HTTPStatus.OK}
                if not account:
                    return generic
            else:  # mail change: the NEW address must not already be registered
                generic = {'message': '若可變更，將寄出驗證通知', 'stateCode': HTTPStatus.OK}
                if account:
                    return generic
            
            code = generate_verification_code()
            self.redis.setex(
                f"{mode}Code:{formatted_email}",
                settings.RESET_PW_CODE_EXPIRE_TIME * 60,
                code
            )
            return {**generic, 'code': code}
        except Exception:
            return {'message': '若符合條件，通知已寄出', 'stateCode': HTTPStatus.OK}
    
    def reset_password(self, email: str, code: str, new_password: str) -> Optional[Dict[str, Any]]:
        """Reset password with verification code."""
        try:
            formatted_email = format_email(email)
            account = self.account_repo.get_by_email(formatted_email)
            
            # Uniform response: never reveal whether the address is registered.
            invalid = {'error': '驗證碼錯誤或已失效', 'stateCode': HTTPStatus.FORBIDDEN}
            if not account:
                return invalid
            
            # Verify code from Redis (constant-ish; missing account handled above)
            stored_code = self.redis.get(f"pwCode:{formatted_email}")
            if not stored_code:
                return invalid
            stored_str = stored_code.decode() if isinstance(stored_code, bytes) else stored_code
            if stored_str != code:
                return invalid
            
            # Delete code from Redis
            self.redis.delete(f"pwCode:{formatted_email}")
            
            # Update password
            account.password = hash_password(new_password)
            self.account_repo.update(account)
            
            # Invalidate all sessions
            self.sign_out(account.id)
            
            return {'message': 'success', 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
    
    def verify_email(self, user_id: int, hash: str, signature: str = None) -> Optional[Dict[str, Any]]:
        """Verify email with signed URL (Laravel style)."""
        try:
            account = self.account_repo.get_by_id(user_id)
            
            if not account:
                return {'error': '使用者不存在', 'stateCode': HTTPStatus.NOT_FOUND}
            
            # Verify using Redis
            if not verify_signed_url(user_id, hash, signature, self.redis):
                return {'error': '驗證連結無效或已過期', 'stateCode': HTTPStatus.FORBIDDEN}
            
            # Delete from Redis
            self.redis.delete(f"registerVerifyMail:{user_id}")
            
            # Update account
            account.email_verified_at = datetime.utcnow()
            account.enable = True
            self.account_repo.update(account)
            
            return {'message': 'Email verified successfully.', 'stateCode': HTTPStatus.OK}
        except Exception as e:
            return {'error': '操作失敗，請稍後再試', 'stateCode': HTTPStatus.INTERNAL_SERVER_ERROR}
