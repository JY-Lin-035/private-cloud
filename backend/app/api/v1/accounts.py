from fastapi import APIRouter, Depends, HTTPException, Request, Response, Query
from sqlalchemy.orm import Session
from redis import Redis
import json
from app.schemas.account import (
    RegisterRequest, LoginRequest, ModifyEmailRequest, 
    ModifyPasswordRequest, ResetPasswordRequest, GetCodeRequest,
    LoginResponse, MessageResponse, ErrorResponse
)
from app.services.account_service import AccountService
from app.services.email_service import EmailService
from app.tasks.email_tasks import celery_app
from app.api.dependencies import get_db, get_redis, get_current_user_id, get_current_user, get_email_service
from app.api.rate_limit import rate_limit
from app.config import settings
from app.utils import logger as log
from app.utils.session_auth import verify_session_value
from app.models.account import Account
from app.constants import Identity
from sqlalchemy import select, func

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
logger = log.get_logger("accounts_api.log")


@router.post("/register", dependencies=[Depends(rate_limit(5, 300))])
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    email_service: EmailService = Depends(get_email_service)
):
    """Register a new account."""
    from app.services.feature_flag_service import is_feature_enabled
    if not is_feature_enabled("allow_registration"):
        raise HTTPException(status_code=403, detail="註冊功能暫時關閉，如有需要請聯絡管理員。")
    if not is_feature_enabled("enable_verification_email"):
        raise HTTPException(status_code=403, detail="郵件驗證服務暫時無法使用，目前無法註冊。請稍後再試或聯絡管理員。")
    try:
        logger.info("Register request received")
        
        account_service = AccountService(db, redis_client)
        
        logger.info("Calling account service register")
        result = account_service.register(request.username, request.email, request.password)
        logger.info(f"Account service result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Registration error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        # Queue verification email
        logger.info("Getting account by name")
        account = account_service.account_repo.get_by_name(request.username)
        if account:
            logger.info(f"Sending verification email, account_id: {account.id}, email: {account.email}")
            email_service.send_verification_email(account.id, account.email)
        
        logger.info("Registration successful")
        return {"message": "success"}
    except Exception as e:
        logger.error(f"Register endpoint error: {e}")
        raise


@router.post("/login", dependencies=[Depends(rate_limit(5, 30))])
def login(
    http_request: Request,
    request: LoginRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    email_service: EmailService = Depends(get_email_service)
):
    """Login user."""
    try:
        logger.info("Login request received")
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.login(request.username, request.password, email_service)
        
        if result and 'error' in result:
            logger.error(f"Login error: {result['error']}, stateCode: {result['stateCode']}")
            try:
                from app.services import security_engine
                from app.utils.client_ip import request_client_ip
                if result.get('stateCode') == 401:
                    security_engine.record_event(
                        "login_fail", request_client_ip(http_request),
                        request.username, None, str(result.get('error', '')))
            except Exception:
                pass
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        response = Response(
            content=json.dumps({"message": "登入成功", "email": result['email']}),
            media_type="application/json",
        )

        response.set_cookie(
            key="session",
            value=result['token'],
            max_age=settings.TOKEN_EXPIRE_TIME * 60,
            path="/",  # Important: cookie available site-wide
            httponly=True,
            samesite=settings.COOKIE_SAMESITE,
            secure=True
        )
        
        logger.info("Login successful")
        return response
    except Exception as e:
        logger.error(f"Login endpoint error: {e}")
        raise


@router.post("/signOut")
def sign_out(
    request: Request,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Sign out user."""
    try:
        from app.api.v1.preview import revoke_preview_tokens_for_user
        revoke_preview_tokens_for_user(redis_client, user_id)
        logger.info(f"Sign out request received, user_id: {user_id}")
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.sign_out(user_id)
        logger.info(f"Sign out result: {result.get('error') if isinstance(result, dict) else 'ok'}")
        
        if result and 'error' in result:
            logger.error(f"Sign out error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])

        try:
            from app.services import collab_events
            collab_events.revoke_user(user_id, "sign out")
        except Exception:
            pass
        
        response = Response(status_code=200)
        response.delete_cookie(key="session", path="/")
        
        logger.info("Sign out successful")
        return response
    except Exception as e:
        logger.error(f"Sign out endpoint error: {e}")
        raise


@router.post("/getCode", dependencies=[Depends(rate_limit(1, 30))])
def get_code(
    request: GetCodeRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Get verification code."""
    from app.services.feature_flag_service import is_feature_enabled
    if not is_feature_enabled("enable_auth_code_email"):
        raise HTTPException(status_code=403, detail="驗證碼郵件服務暫時關閉，密碼重設／信箱變更暫時不可用。請稍後再試或聯絡管理員。")
    try:
        logger.info(f"Get code processing mode={request.mode}")
        
        account_service = AccountService(db, redis_client)
        email_service = EmailService(celery_app)
        
        result = account_service.get_code(request.email, request.mode)
        logger.info(f"Get code processing mode={request.mode}")
        
        if result and 'error' in result:
            logger.error(f"Get code error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        # The service generated and stored the code; e-mail the same one.
        code = result.get('code') if isinstance(result, dict) else None
        if code:
            mode_titles = {'pw': '密碼重置通知', 'mail': '信箱變更驗證通知'}
            email_service.send_code_email(request.email, code, mode_titles.get(request.mode, '驗證碼通知'))
        
        logger.info("Verification code processed")
        return {"message": result.get('message', '若此信箱符合條件，通知已寄出')}
    except Exception as e:
        logger.error(f"Get code endpoint error: {e}")
        raise


@router.put("/modifyMail")
def modify_mail(
    request: ModifyEmailRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Modify user email."""
    try:
        logger.info(f"Modify mail request received, user_id: {user_id}, email: {request.email}")
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.modify_email(user_id, request.email, request.check_email, request.code)
        logger.info(f"Modify mail result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Modify mail error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Email modified successfully")
        return {"email": result['email']}
    except Exception as e:
        logger.error(f"Modify mail endpoint error: {e}")
        raise


@router.put("/modifyPassword")
@router.put("/modifyPW")
def modify_password(
    request: ModifyPasswordRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Modify user password."""
    try:
        logger.info(f"Modify password request received, user_id: {user_id}")
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.modify_password(user_id, request.now_pw, request.new_pw)
        logger.info(f"Modify password result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Modify password error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Password modified successfully")
        return {"message": "success"}
    except Exception as e:
        logger.error(f"Modify password endpoint error: {e}")
        raise


@router.put("/resetPW", dependencies=[Depends(rate_limit(2, 30))])
def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Reset password with verification code."""
    try:
        logger.info(f"Reset password request received, email: {request.email}")
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.reset_password(request.email, request.code, request.password)
        logger.info(f"Reset password result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Reset password error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        logger.info("Password reset successfully")
        return {"message": "success"}
    except Exception as e:
        logger.error(f"Reset password endpoint error: {e}")
        raise


@router.get("/checkSession")
def check_session(request: Request, redis_client: Redis = Depends(get_redis)):
    """Read-only session probe used by the SPA bootstrap.

    Deliberately does NOT extend the session TTL (a background check must
    not keep an otherwise idle session alive — same policy as the
    middleware's no-renew list) and verifies the cookie constant-time via
    the shared session_auth helper instead of duplicating the logic here.
    """
    try:
        user_dict = verify_session_value(redis_client, request.cookies.get('session'))
        if not user_dict:
            return {"authenticated": False}

        logger.info(f"Check session valid, user_id: {user_dict.get('user_id')}, identity: {user_dict.get('identity')}")
        return {
            "authenticated": True,
            "id": user_dict.get("user_id"),
            "username": user_dict.get("username"),
            "email": user_dict.get("email"),
            "identity": user_dict.get("identity")
        }
    except Exception as e:
        logger.error(f"Check session endpoint error: {e}")
        return {"authenticated": False}


@router.post("/admin/recalculate-user-storage")
def recalculate_user_storage(
    username: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Recalculate storage usage for a specific user (admin only)."""
    _admin_required(request)
    from app.models.file import File
    from app.models.folder import Folder
    from sqlalchemy import select

    target_user = db.query(Account).filter(Account.name == username.strip()).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="User not found")

    folders = db.execute(
        select(Folder).where(Folder.owner_id == target_user.id)
    ).scalars().all()

    total_size = 0
    for folder in folders:
        # Include soft-deleted files: they still occupy disk and count toward
        # quota by design, so recalculation must not free quota for trashed data.
        files = db.execute(
            select(File).where(
                File.parent_folder_id == folder.uuid,
            )
        ).scalars().all()
        actual_size = sum(f.size for f in files)
        folder.size = actual_size
        total_size += actual_size

    target_user.used_size = total_size
    db.commit()

    logger.info(f"Storage recalculation completed for user {username}: {total_size} bytes")
    return {
        "message": "Storage recalculation completed",
        "username": username,
        "total_size": total_size,
        "folders_updated": len(folders),
    }

def _admin_required(request) -> dict:
    # Delegate to the single require_admin dependency so admin gating (and its
    # admin_probe scoring) has exactly one implementation.
    from app.api.dependencies import require_admin
    return require_admin(request)


@router.get("/admin/users")
def admin_list_users(
    request: Request,
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    search: str = Query("", max_length=100),
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    _admin_required(request)
    logger.info(f"[Admin] list users page={page} per_page={per_page} search={search}")
    query = db.query(Account).filter(Account.identity != Identity.ADMIN)
    if search:
        pat = f"%{search}%"
        query = query.filter(Account.name.ilike(pat) | Account.email.ilike(pat))
    total = query.count()
    users = query.offset((page - 1) * per_page).limit(per_page).all()
    result = []
    for u in users:
        online = bool(redis_client.exists(f"session:{u.id}"))
        us = u.used_size or 0
        ts = u.total_file_size or 0
        result.append({
            "id": u.id,
            "username": u.name,
            "email": u.email,
            "used_storage": us,
            "total_storage": ts,
            "enabled": bool(u.enable),
            "online": online
        })
    return {
        "users": result,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": max(1, (total - 1) // per_page + 1)
    }


@router.put("/admin/users/{user_id}/quota")
def admin_update_quota(
    request: Request,
    user_id: int,
    total_storage: int = Query(..., ge=0),
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    _admin_required(request)
    account = db.query(Account).filter(Account.id == user_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    if account.identity == Identity.ADMIN and account.id != getattr(request.state, 'user_id', None):
        raise HTTPException(status_code=403, detail="Cannot modify another admin account")
    used = account.used_size or 0
    if total_storage < used:
        raise HTTPException(status_code=400, detail=f"無法設定低於目前已使用容量的上限（已使用 {used} bytes）")
    account.total_file_size = total_storage
    db.commit()
    from app.utils.security_log import write_event
    write_event("quota_change", None, str(request.state.user_id), f"user#{user_id}", f"quota={total_storage}")
    return {"message": "success", "total_storage": total_storage}


@router.post("/admin/users/{user_id}/force-logout")
def admin_force_logout(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    _admin_required(request)
    account = db.query(Account).filter(Account.id == user_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    if account.identity == Identity.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot force logout admin")
    redis_client.delete(f"session:{user_id}")
    redis_client.delete(f"session_data:{user_id}")
    try:
        from app.services import collab_events
        collab_events.revoke_user(user_id, "force logout")
    except Exception:
        pass
    return {"message": "User logged out successfully"}


@router.put("/admin/users/{user_id}/toggle-enable")
def admin_toggle_enable(
    request: Request,
    user_id: int,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    _admin_required(request)
    account = db.query(Account).filter(Account.id == user_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    if account.identity == Identity.ADMIN:
        raise HTTPException(status_code=403, detail="Cannot disable admin user")
    account.enable = not account.enable
    db.commit()
    if not account.enable:
        redis_client.delete(f"session:{user_id}")
        redis_client.delete(f"session_data:{user_id}")
        try:
            from app.services import collab_events
            collab_events.revoke_user(user_id, "account disabled")
        except Exception:
            pass
        from app.utils.security_log import write_event
        from app.utils.client_ip import request_client_ip
        write_event("account_suspend", request_client_ip(request),
                    str(getattr(request.state, "user_id", "?")), account.name, "admin 開關停用，session 已失效")
    return {"enabled": account.enable}


@router.put("/quota/self")
def update_own_quota(
    request: Request,
    total_storage: int = Query(..., ge=0),
    db: Session = Depends(get_db),
):
    """Update the signed-in admin's own storage quota."""
    _admin_required(request)
    user_id = getattr(request.state, 'user_id', None)
    account = db.query(Account).filter(Account.id == user_id).first()
    if not account:
        raise HTTPException(status_code=404, detail="User not found")
    used = account.used_size or 0
    if total_storage < used:
        raise HTTPException(status_code=400, detail=f"無法設定低於目前已使用容量的上限（已使用 {used} bytes）")
    account.total_file_size = total_storage
    db.commit()
    from app.utils.security_log import write_event
    write_event("quota_change", None, str(user_id), "self", f"quota={total_storage}")
    logger.info(f"[Admin] self quota updated user_id={user_id} total_storage={total_storage}")
    return {"message": "success", "total_storage": total_storage}
