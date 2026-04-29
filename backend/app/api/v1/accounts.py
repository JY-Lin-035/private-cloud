from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from redis import Redis
from app.schemas.account import (
    RegisterRequest, LoginRequest, ModifyEmailRequest, 
    ModifyPasswordRequest, ResetPasswordRequest, GetCodeRequest,
    LoginResponse, MessageResponse, ErrorResponse
)
from app.services.account_service import AccountService
from app.services.email_service import EmailService
from app.tasks.email_tasks import celery_app
from app.api.dependencies import get_db, get_redis, get_current_user_id, get_email_service, get_account_service
from app.api.rate_limit import rate_limit
from app.utils import logger as log

router = APIRouter(prefix="/api/accounts", tags=["accounts"])
logger = log.get_logger("accounts_api.log")


@router.post("/register", dependencies=[Depends(rate_limit(5, 300))])
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    email_service: EmailService = Depends(get_email_service)
):
    """Register a new account."""
    try:
        logger.info(f"Register request received, username: {request.username}, email: {request.email}")
        
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
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    email_service: EmailService = Depends(get_email_service)
):
    """Login user."""
    try:
        logger.info(f"Login request received, username: {request.username}")
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.login(request.username, request.password, email_service)
        logger.info(f"Login result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Login error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        response = Response(
            content='{"message": "登入成功", "email": "' + result['email'] + '"}', 
            media_type="application/json", 
        )

        response.set_cookie(
            key="session",
            value=result['token'],
            max_age=30 * 60,  # 30 minutes
            path="/",  # Important: cookie available site-wide
            httponly=True,
            samesite="lax",
            secure=False
        )
        
        logger.info("Login successful")
        return response
    except Exception as e:
        logger.error(f"Login endpoint error: {e}")
        raise


@router.post("/signOut")
async def sign_out(
    request: Request,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id)
):
    """Sign out user."""
    try:
        logger.info(f"Sign out request received, user_id: {user_id}")
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.sign_out(user_id)
        logger.info(f"Sign out result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Sign out error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        response = Response(status_code=200)
        response.delete_cookie(key="session", path="/")
        
        logger.info("Sign out successful")
        return response
    except Exception as e:
        logger.error(f"Sign out endpoint error: {e}")
        raise


@router.post("/getCode", dependencies=[Depends(rate_limit(1, 30))])
async def get_code(
    request: GetCodeRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Get verification code."""
    try:
        logger.info(f"Get code request received, email: {request.email}, mode: {request.mode}")
        
        account_service = AccountService(db, redis_client)
        email_service = EmailService(celery_app)
        
        result = account_service.get_code(request.email, request.mode)
        logger.info(f"Get code result: {result}")
        
        if result and 'error' in result:
            logger.error(f"Get code error: {result['error']}, stateCode: {result['stateCode']}")
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        # Queue code email
        from app.utils.security import generate_verification_code
        code = generate_verification_code()
        redis_client.setex(
            f"{request.mode}Code:{request.email}",
            5 * 60,  # 5 minutes
            code
        )
        
        mode_titles = {'pw': '密碼重置通知', 'mail': '信箱變更驗證通知'}
        email_service.send_code_email(request.email, code, mode_titles.get(request.mode, '驗證碼通知'))
        
        logger.info("Verification code sent")
        return {"message": "請至信箱查看通知"}
    except Exception as e:
        logger.error(f"Get code endpoint error: {e}")
        raise


@router.put("/modifyMail")
async def modify_mail(
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
async def modify_password(
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
async def reset_password(
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
async def check_session(user_id: int = Depends(get_current_user_id)):
    """Check if user session is valid."""
    try:
        logger.info(f"Check session request received, user_id: {user_id}")
        logger.info("Session valid")
        return Response(status_code=200)
    except Exception as e:
        logger.error(f"Check session endpoint error: {e}")
        raise HTTPException(status_code=401, detail="Unauthorized")


@router.post("/admin/recalculate-user-storage")
async def recalculate_user_storage(
    username: str,
    user_id: int = Depends(get_current_user_id),
    db: Session = Depends(get_db),
    account_service: AccountService = Depends(get_account_service)
):
    """Recalculate storage usage for a specific user (admin only)."""
    try:
        # Check if user is admin (identity == 1)
        account = account_service.get_by_id(user_id)
        if not account or account.identity != 1:
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get target user by username
        target_user = account_service.get_by_username(username)
        if not target_user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Recalculate storage for the target user
        from app.services.file_service import FileService
        from app.services.folder_service import FolderService
        from app.repositories.file_repository import FileRepository
        from app.repositories.folder_repository import FolderRepository
        from app.models.file import File
        from app.models.folder import Folder
        from sqlalchemy import select
        import os
        
        file_repo = FileRepository(db)
        folder_repo = FolderRepository(db)
        file_service = FileService(db, file_repo, folder_repo)
        folder_service = FolderService(db, folder_repo, account_repo)
        
        logger.info(f"Starting storage recalculation for user: {username}")
        
        # Get all folders for the user
        folders = db.execute(
            select(Folder).where(Folder.owner_id == target_user.id)
        ).scalars().all()
        
        total_size = 0
        
        # Recalculate each folder size
        for folder in folders:
            # Calculate actual size from files in this folder
            files = db.execute(
                select(File).where(
                    File.parent_folder_id == folder.uuid,
                    File.deleted_at.is_(None)
                )
            ).scalars().all()
            
            actual_size = sum(file.size for file in files)
            
            # Update folder size
            folder.size = actual_size
            total_size += actual_size
        
            logger.info(f"Updated folder {folder.name}: {actual_size} bytes")
        
        # Update account used size
        target_user.used_size = total_size
        
        db.commit()
        
        logger.info(f"Storage recalculation completed for user {username}: {total_size} bytes")
        
        return {
            "message": "Storage recalculation completed",
            "username": username,
            "total_size": total_size,
            "folders_updated": len(folders)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Storage recalculation error: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")
