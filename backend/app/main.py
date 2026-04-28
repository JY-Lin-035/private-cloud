import traceback as tb
from redis import Redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


from app.config import settings

from app.models.base import Base
from app.models.account import Account

from app.utils import logger as log

from app.api.dependencies import get_redis
from app.api.v1 import accounts, files, folders, share

from app.middleware.session_middleware import SessionMiddleware
from app.middleware.rate_limit_middleware import RateLimitMiddleware

# Create FastAPI app
app = FastAPI(title="File Management Backend", version="1.0.0")

# Logger
logger = log.get_logger("main.log")

# Add CORS middleware - must use explicit origins when credentials=True
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Database setup
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Redis client
redis_client = Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True
)

# Add middleware
app.add_middleware(SessionMiddleware, redis_client=redis_client)
rate_limit_middleware = RateLimitMiddleware(redis_client)


# Global exception handler for debugging
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"ERROR: {exc}")
    print(f"TRACEBACK:\n{tb.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": str(exc), "traceback": tb.format_exc()}
    )

# Include routers
app.include_router(accounts.router)
app.include_router(files.router)
app.include_router(folders.router)
app.include_router(share.router)


@app.get("/api/email/verify/{user_id}/{hash}")
async def verify_email(user_id: int, hash: str, signature: str = None):
    """Verify email with signed URL."""
    from sqlalchemy.orm import Session
    from app.services.account_service import AccountService
    
    db = SessionLocal()
    try:
        logger.info(f"Email verification request received, user_id: {user_id}")
        
        account_service = AccountService(db, redis_client)
        result = account_service.verify_email(user_id, hash, signature)
        
        if result and 'error' in result:
            logger.error(f"Email verification error: {result['error']}, stateCode: {result['stateCode']}")
            return JSONResponse(status_code=result['stateCode'], content={"error": result['error']})
        
        logger.info("Email verified successfully")
        return {"message": "Email verified successfully."}
    except Exception as e:
        logger.error(f"Email verification endpoint error: {e}")
        raise
    finally:
        db.close()


@app.get("/")
async def root():
    """Root endpoint."""
    return {"message": "File Management Backend API"}


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
