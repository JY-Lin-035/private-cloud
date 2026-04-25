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
from app.api.dependencies import get_db, get_redis, get_current_user_id, get_email_service
from app.api.rate_limit import rate_limit
from app.utils.logger_sample import log_info, log_error

router = APIRouter(prefix="/api/accounts", tags=["accounts"])


@router.post("/register", dependencies=[Depends(rate_limit(5, 300))])
async def register(
    request: RegisterRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis),
    email_service: EmailService = Depends(get_email_service)
):
    """Register a new account."""
    try:
        log_info("Register request received", {"username": request.username, "email": request.email})
        
        account_service = AccountService(db, redis_client)
        
        log_info("Calling account service register")
        result = account_service.register(request.username, request.email, request.password)
        log_info("Account service result", {"result": result})
        
        if result and 'error' in result:
            log_info("Registration error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        # Queue verification email
        log_info("Getting account by name")
        account = account_service.account_repo.get_by_name(request.username)
        if account:
            log_info("Sending verification email", {"account_id": account.id, "email": account.email})
            email_service.send_verification_email(account.id, account.email)
        
        log_info("Registration successful")
        return {"message": "success"}
    except Exception as e:
        log_error("Register endpoint error", e)
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
        log_info("Login request received", {"username": request.username})
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.login(request.username, request.password, email_service)
        log_info("Login result", {"result": result})
        
        if result and 'error' in result:
            log_info("Login error", {"error": result['error'], "stateCode": result['stateCode']})
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
        
        log_info("Login successful")
        return response
    except Exception as e:
        log_error("Login endpoint error", e)
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
        log_info("Sign out request received", {"user_id": user_id})
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.sign_out(user_id)
        log_info("Sign out result", {"result": result})
        
        if result and 'error' in result:
            log_info("Sign out error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        response = Response(status_code=200)
        response.delete_cookie(key="session", path="/")
        
        log_info("Sign out successful")
        return response
    except Exception as e:
        log_error("Sign out endpoint error", e)
        raise


@router.post("/getCode", dependencies=[Depends(rate_limit(1, 30))])
async def get_code(
    request: GetCodeRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Get verification code."""
    try:
        log_info("Get code request received", {"email": request.email, "mode": request.mode})
        
        account_service = AccountService(db, redis_client)
        email_service = EmailService(celery_app)
        
        result = account_service.get_code(request.email, request.mode)
        log_info("Get code result", {"result": result})
        
        if result and 'error' in result:
            log_info("Get code error", {"error": result['error'], "stateCode": result['stateCode']})
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
        
        log_info("Verification code sent")
        return {"message": "請至信箱查看通知"}
    except Exception as e:
        log_error("Get code endpoint error", e)
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
        log_info("Modify mail request received", {"user_id": user_id, "email": request.email})
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.modify_email(user_id, request.email, request.check_email, request.code)
        log_info("Modify mail result", {"result": result})
        
        if result and 'error' in result:
            log_info("Modify mail error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Email modified successfully")
        return {"email": result['email']}
    except Exception as e:
        log_error("Modify mail endpoint error", e)
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
        log_info("Modify password request received", {"user_id": user_id})
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.modify_password(user_id, request.now_pw, request.new_pw)
        log_info("Modify password result", {"result": result})
        
        if result and 'error' in result:
            log_info("Modify password error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Password modified successfully")
        return {"message": "success"}
    except Exception as e:
        log_error("Modify password endpoint error", e)
        raise


@router.put("/resetPW", dependencies=[Depends(rate_limit(2, 30))])
async def reset_password(
    request: ResetPasswordRequest,
    db: Session = Depends(get_db),
    redis_client: Redis = Depends(get_redis)
):
    """Reset password with verification code."""
    try:
        log_info("Reset password request received", {"email": request.email})
        
        account_service = AccountService(db, redis_client)
        
        result = account_service.reset_password(request.email, request.code, request.password)
        log_info("Reset password result", {"result": result})
        
        if result and 'error' in result:
            log_info("Reset password error", {"error": result['error'], "stateCode": result['stateCode']})
            raise HTTPException(status_code=result['stateCode'], detail=result['error'])
        
        log_info("Password reset successfully")
        return {"message": "success"}
    except Exception as e:
        log_error("Reset password endpoint error", e)
        raise


@router.get("/checkSession")
async def check_session(user_id: int = Depends(get_current_user_id)):
    """Check if user session is valid."""
    try:
        log_info("Check session request received", {"user_id": user_id})
        log_info("Session valid")
        return Response(status_code=200)
    except Exception as e:
        log_error("Check session endpoint error", e)
        raise HTTPException(status_code=401, detail="Unauthorized")
