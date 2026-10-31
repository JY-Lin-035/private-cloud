from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session
from redis import Redis
from typing import Optional
from app.config import settings
from app.database import SessionLocal
from app.services.email_service import EmailService
from app.tasks.email_tasks import celery_app


def get_db():
    """Get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


_shared_redis = None


def get_redis():
    """Get shared Redis client (connection pool reused across requests)."""
    global _shared_redis
    if _shared_redis is None:
        _shared_redis = Redis.from_url(settings.REDIS_URL)
    yield _shared_redis


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


def require_admin(request: Request) -> dict:
    """Ensure the authenticated user is an admin; returns the user dict."""
    from app.constants import Identity
    if not hasattr(request.state, 'user'):
        raise HTTPException(status_code=401, detail="Unauthorized")
    if request.state.user.get("identity") != Identity.ADMIN:
        # Score probes for state-changing attempts only: a signed-in non-admin
        # could otherwise be griefed into admin_probe strikes / auto-disable
        # by tricking them into top-level GET navigations of admin URLs.
        # (Read attempts still get 403; they just do not feed the scoring pool.)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            try:
                from app.services import security_engine
                from app.utils.client_ip import request_client_ip
                ip = request_client_ip(request)
                security_engine.record_event(
                    "admin_probe", ip, str(request.state.user.get("username") or request.state.user.get("id")),
                    request.url.path, "非管理員存取 admin 端點")
            except Exception:
                pass
        raise HTTPException(status_code=403, detail="Admin only")
    return request.state.user


def get_current_user_id_optional(request: Request) -> Optional[int]:
    """Get current authenticated user ID or None if not authenticated."""
    if hasattr(request.state, 'user_id'):
        return request.state.user_id
    return None


def get_current_user_id(request: Request):
    """Get current authenticated user ID from request state."""
    if not hasattr(request.state, 'user_id'):
        raise HTTPException(status_code=401, detail="Unauthorized")
    return request.state.user_id