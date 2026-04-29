from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from redis import Redis
from typing import Optional
from app.config import settings
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.services.email_service import EmailService
from app.services.account_service import AccountService
from app.repositories.account_repository import AccountRepository
from app.tasks.email_tasks import celery_app

# Database engine
engine = create_engine(settings.DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_redis():
    """Get Redis client."""
    redis_client = Redis.from_url(settings.REDIS_URL)
    try:
        yield redis_client
    finally:
        redis_client.close()


def get_email_service(redis_client: Redis = Depends(get_redis)):
    """Get email service instance."""
    email_service = EmailService(celery_app, redis_client)
    try:
        yield email_service
    finally:
        pass


def get_current_user(request: Request):
    """Get current authenticated user from request state."""
    if not hasattr(request.state, 'user'):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return request.state.user


def get_account_service(db: Session = Depends(get_db)):
    """Get account service instance."""
    account_repo = AccountRepository(db)
    account_service = AccountService(account_repo)
    try:
        yield account_service
    finally:
        pass


def get_current_user_id(request: Request):
    """Get current authenticated user ID from request state."""
    if not hasattr(request.state, 'user_id'):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return request.state.user_id
