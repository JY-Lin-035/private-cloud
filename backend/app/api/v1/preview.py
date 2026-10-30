"""Sandbox-safe raw content delivery and Office conversion endpoints (P3).

raw: serves html/htm/xhtml/svg for preview. Auth is a single-use bearer
token (previewToken), NEVER the session cookie; responses are locked down
with `CSP: sandbox` (opaque origin) + nosniff + no-store.

Office documents are rendered fully client-side (see frontend OfficeFrame);
the server never parses them.
"""
import os
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel
from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, get_redis, get_current_user_id
from app.api.rate_limit import rate_limit
from app.config import settings
from app.models.file import File
from app.models.folder import Folder
from app.services import batch_ops
from app.services.feature_flag_service import is_feature_enabled
from app.utils import logger as log
from app.utils.file_classes import MAX_EDIT_BYTES, SANDBOX_EXTS, ext_of

router = APIRouter(prefix="/api/files", tags=["preview"])
logger = log.get_logger("preview_api.log")

PV_TTL = 600
# Trusted origins come from settings (single source shared with CORS/OriginGuard)
# so there is no second hardcoded list that can drift.

_SANDBOX_MIME = {"html": "text/html", "htm": "text/html", "xhtml": "application/xhtml+xml", "svg": "image/svg+xml"}


def _require_preview_flag():
    if not is_feature_enabled("enable_file_preview", default=False):
        raise HTTPException(status_code=403, detail="檔案預覽功能尚未啟用")


class PreviewTokenRequest(BaseModel):
    uuid: str


@router.post("/previewToken", dependencies=[Depends(rate_limit(30, 60))])
async def issue_preview_token(
    request: PreviewTokenRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    _require_preview_flag()
    origin = http_request.headers.get("origin")
    if origin and origin not in settings.allowed_origins:
        raise HTTPException(status_code=403, detail="來源不受信任")
    f = db.execute(select(File).where(File.uuid == request.uuid, File.owner_id == user_id)).scalar_one_or_none()
    if f is None or f.deleted_at is not None or ext_of(f.name) not in SANDBOX_EXTS:
        raise HTTPException(status_code=404, detail="檔案不存在或不支援沙箱預覽")
    batch_ops.assert_not_deleting(redis, f.uuid)
    token = secrets.token_urlsafe(32)
    redis.setex(f"pv:{token}", PV_TTL, f"{user_id}|{f.uuid}")
    try:
        r = redis
        key = f"pvby:{user_id}"
        pipe = r.pipeline()
        pipe.sadd(key, token)
        pipe.expire(key, PV_TTL + 60)
        pipe.execute()
    except Exception:
        pass
    return {"token": token, "ttl": PV_TTL}


def _sandbox_headers(f: File) -> dict:
    mime = _SANDBOX_MIME.get(ext_of(f.name), "text/plain")
    return {
        "Content-Type": mime,
        "Content-Security-Policy": "sandbox allow-scripts",
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "no-store",
        "X-Robots-Tag": "noindex, nofollow",
    }


@router.get("/raw", dependencies=[Depends(rate_limit(120, 60))])
async def preview_raw(
    uuid: str = Query(...),
    ptk: str = Query(...),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
):
    """Serve sandbox-preview content. Token-bound; session cookie is NOT used."""
    _require_preview_flag()
    bound = redis.getdel(f"pv:{ptk}")  # single-use: consumed on redemption
    if not bound:
        raise HTTPException(status_code=401, detail="預覽憑證無效或已逾期")
    if isinstance(bound, bytes):
        bound = bound.decode()
    try:
        uid_s, uuid_s = bound.split("|", 1)
        uid = int(uid_s)
    except ValueError:
        raise HTTPException(status_code=401, detail="預覽憑證無效")
    if uuid_s != uuid:
        raise HTTPException(status_code=403, detail="憑證與檔案不符")
    batch_ops.assert_not_deleting(redis, uuid)
    f = db.execute(select(File).where(File.uuid == uuid, File.owner_id == uid)).scalar_one_or_none()
    if f is None or f.deleted_at is not None or ext_of(f.name) not in SANDBOX_EXTS:
        raise HTTPException(status_code=404, detail="檔案不存在")
    if (f.size or 0) > MAX_EDIT_BYTES:
        raise HTTPException(status_code=413, detail="檔案過大")
    path = os.path.join(settings.STORAGE_BASE_PATH, f.uuid)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="檔案內容不存在")
    with open(path, "rb") as fh:
        data = fh.read()
    return Response(content=data, status_code=200, headers=_sandbox_headers(f))


def revoke_preview_tokens_for_user(redis, user_id: int) -> None:
    """Best-effort revocation of outstanding preview tokens at sign-out."""
    try:
        key = f"pvby:{user_id}"
        toks = redis.smembers(key)
        for t in toks or []:
            if isinstance(t, bytes):
                t = t.decode()
            redis.delete(f"pv:{t}")
        redis.delete(key)
    except Exception:
        pass
