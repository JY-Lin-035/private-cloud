import traceback as tb
import threading
import time
import logging
import re as _re
from redis import Redis
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware


# --- credential masking in the uvicorn access log -------------------------
# Request lines carry bearer-style query params (?link=<32-hex share token>,
# ?ticket=<signed share hash + ts + sig>, ?token=/?ptk= one-time tokens).
# The share link is a LONG-LIVED credential and must never land in access
# logs in full. NOTE: uvicorn's AccessFormatter unpacks record.args (5-tuple,
# element 2 = "method path proto"); we must rewrite that element IN PLACE and
# never clear args, or every request line raises a logging error and is lost.
class _AccessLogSecretFilter(logging.Filter):
    # NOTE: param NAMES written in percent-encoded form (e.g. %74icket=) are
    # not matched here; the Cloudflare edge normalizes percent-encodings of
    # unreserved characters before reaching us, and the value-encoded variant
    # IS covered ('%' in the class). Direct loopback clients are out of the
    # remote threat model (documented, non-blocking per security review R9).
    _PATTERN = _re.compile(
        r"([?&](?:link|token|ptk|ticket)=)([0-9A-Za-z_.%-]{6})[0-9A-Za-z_.%-]+"
    )

    def _redact(self, s):
        return self._PATTERN.sub(r"\1\2…", s)

    def filter(self, record):
        try:
            args = record.args
            if isinstance(args, tuple):
                # Scan every string element instead of assuming a fixed
                # position so a uvicorn arg-order change can't re-leak.
                changed = False
                mutable = list(args)
                for i, a in enumerate(mutable):
                    if isinstance(a, str):
                        red = self._redact(a)
                        if red != a:
                            mutable[i] = red
                            changed = True
                if changed:
                    record.args = tuple(mutable)
            else:
                msg = record.getMessage()
                red = self._redact(msg)
                if red != msg:
                    record.msg = red
                    record.args = None
        except Exception:
            pass
        return True


logging.getLogger("uvicorn.access").addFilter(_AccessLogSecretFilter())


def _attach_access_log_filter():
    lg = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, _AccessLogSecretFilter) for f in lg.filters):
        lg.addFilter(_AccessLogSecretFilter())


from app.config import settings
from app.database import SessionLocal

from app.models.base import Base
from app.models.account import Account

from app.utils import logger as log

from app.api.dependencies import get_redis
from app.api.v1 import accounts, files, folders, share, collaboration, collab_ws, preview
from app.api.v1 import settings as settings_api
from app.api.v1 import announcements
from app.api.v1 import ipcontrol

from app.middleware.session_middleware import SessionMiddleware
from app.middleware.throttle import ThrottleMiddleware
from app.middleware.origin_guard import OriginGuardMiddleware
from app.services.snapshot_service import auto_save_to_disk, save_snapshot
from app.services import collab_events

# API docs are disabled by default. When ENABLE_API_DOCS is set they are
# registered separately below and restricted to direct loopback access.
app = FastAPI(
    title="File Management Backend",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

# Logger
logger = log.get_logger("main.log")


# (engine and SessionLocal imported from app.database above)
# Redis client
redis_client = Redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_timeout=5,
    retry_on_timeout=True
)

# Add middleware — registration order = inner to outer (last added is OUTERMOST).
# CORS must be outermost so that early responses produced by the session layer
# (401 stale/kicked session) and the throttle layer (429 slow-lane/block) still
# carry Access-Control-Allow-Origin; otherwise browsers report them as opaque
# CORS failures and the frontend 401 interceptor never fires.
app.add_middleware(SessionMiddleware, redis_client=redis_client)
app.add_middleware(ThrottleMiddleware)
app.add_middleware(OriginGuardMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Location",
        "Upload-Offset",
        "Upload-Length",
        "Tus-Resumable",
        "Upload-Complete",
        "Content-Range",
        "Accept-Ranges",
        "Content-Length",
        "ETag",
    ],
)


# ---------------------------------------------------------------- optional docs
def _docs_local_only(request: Request):
    """Allow API docs only for direct loopback access (never through a proxy).

    Cloudflare/nginx always add a proxy header, so remote callers are rejected
    even though Uvicorn sees them from 127.0.0.1.
    """
    from fastapi import HTTPException
    hdrs = {k.lower() for k in request.headers.keys()}
    if hdrs & {"cf-connecting-ip", "x-forwarded-for", "x-real-ip"}:
        raise HTTPException(status_code=404)
    host = request.client.host if request.client else ""
    if host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=404)


if settings.ENABLE_API_DOCS:
    from fastapi import Depends
    from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

    @app.get("/openapi.json", include_in_schema=False, dependencies=[Depends(_docs_local_only)])
    async def _openapi_json():
        return JSONResponse(app.openapi())

    @app.get("/docs", include_in_schema=False, dependencies=[Depends(_docs_local_only)])
    async def _swagger_ui():
        return get_swagger_ui_html(openapi_url="/openapi.json", title="MeowCloud API")

    @app.get("/redoc", include_in_schema=False, dependencies=[Depends(_docs_local_only)])
    async def _redoc_ui():
        return get_redoc_html(openapi_url="/openapi.json", title="MeowCloud API")


# Background scheduler for auto-save and snapshots
def _scheduler():
    elapsed = 0
    while True:
        time.sleep(30)
        elapsed += 30
        try:
            for key in redis_client.scan_iter("collab_content:*"):
                file_uuid = key.replace("collab_content:", "")
                auto_save_to_disk(file_uuid, redis_client)
            if elapsed >= settings.SNAPSHOT_INTERVAL:
                elapsed = 0
                for key in redis_client.scan_iter("collab_content:*"):
                    file_uuid = key.replace("collab_content:", "")
                    save_snapshot(file_uuid, redis_client)
        except Exception:
            pass

threading.Thread(target=_scheduler, daemon=True).start()


@app.on_event("startup")
async def _startup_collab_bus():
    import asyncio
    _attach_access_log_filter()  # re-attach after uvicorn's dictConfig
    collab_events.set_loop(asyncio.get_running_loop())
    collab_events.start()


# Global exception handler for debugging
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error on {request.method} {request.url.path}: {exc}")
    logger.error(f"TRACEBACK:\n{tb.format_exc()}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )

# Include routers
app.include_router(accounts.router)
app.include_router(files.router)
app.include_router(preview.router)
app.include_router(folders.router)
app.include_router(share.router)
app.include_router(collaboration.router)
app.include_router(collab_ws.router)
app.include_router(settings_api.router)
app.include_router(announcements.router)
app.include_router(ipcontrol.router)


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
        return {"message": "Email verified successfully"}
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
    # Real client IP is taken from CF-Connecting-IP via security_engine.
    # proxy_headers must stay ON for the loopback proxy only (forwarded_allow_ips)
    # so X-Forwarded-Proto makes url_for() emit https tus Locations; without it
    # browsers block upload PATCHes as mixed content. Port 8000 is bound to
    # loopback, so remote peers can never feed these headers directly.
    uvicorn.run(app, host="127.0.0.1", port=8000,
                proxy_headers=True, forwarded_allow_ips="127.0.0.1")
