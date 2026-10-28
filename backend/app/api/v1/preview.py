"""Sandbox-safe raw content delivery and Office conversion endpoints (P3).

raw: serves html/htm/xhtml/svg for preview. Auth is a single-purpose bearer
token (previewToken), NEVER the session cookie, and the response is locked
down with `CSP: sandbox` (opaque origin) + nosniff + no-store.

convert: LibreOffice headless -> PDF for office documents, cached on disk,
sandboxed (env isolation, RLIMITs, timeout, best-effort net isolation).
"""
import mimetypes
import os
import secrets
import signal
import subprocess
import tempfile
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response, FileResponse
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
from app.utils.file_classes import (
    MAX_EDIT_BYTES, SANDBOX_EXTS, is_office, is_macro_doc, ext_of,
)

router = APIRouter(prefix="/api/files", tags=["preview"])
logger = log.get_logger("preview_api.log")

PV_TTL = 600
CONVERT_MAX_SRC = 100 * 1024 * 1024
CONVERT_TIMEOUT_S = 120

_SANDBOX_MIME = {"html": "text/html", "htm": "text/html", "xhtml": "application/xhtml+xml", "svg": "image/svg+xml"}


def _require_preview_flag():
    if not is_feature_enabled("enable_file_preview", default=False):
        raise HTTPException(status_code=403, detail="檔案預覽功能尚未啟用")


class PreviewTokenRequest(BaseModel):
    uuid: str


@router.post("/previewToken", dependencies=[Depends(rate_limit(30, 60))])
async def issue_preview_token(
    request: PreviewTokenRequest,
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    _require_preview_flag()
    origin = request.headers.get("origin") if hasattr(request, "headers") else None
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
    bound = redis.get(f"pv:{ptk}")
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


# ---------------- office -> pdf conversion ----------------

def _preview_dir() -> str:
    d = os.path.join(settings.STORAGE_BASE_PATH, ".preview")
    os.makedirs(d, exist_ok=True)
    return d


def _soffice_bin() -> Optional[str]:
    for cand in ("soffice", "libreoffice"):
        try:
            subprocess.run([cand, "--version"], capture_output=True, timeout=10, check=False)
            return cand
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return None


def _limits():
    def preexec():
        os.setpgrp()
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU, (90, 100))
            resource.setrlimit(resource.RLIMIT_FSIZE, (200 * 1024 * 1024, 200 * 1024 * 1024))
            resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))
        except Exception:
            pass
    return preexec


def _run_convert(bin_path: str, src: str, out_dir: str, profile_dir: str) -> bool:
    env = dict(os.environ)
    env["HOME"] = profile_dir
    cmd = [bin_path, "--headless", "--norestore", "--nolockcheck", "--nodefault",
           "--convert-to", "pdf", "--outdir", out_dir, src]
    try:
        r = subprocess.run(["unshare", "-rni", "--map-root-user"] + cmd,
                           env=env, capture_output=True, timeout=CONVERT_TIMEOUT_S,
                           preexec_fn=_limits())
        if os.path.isfile(_first_pdf(out_dir)):
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired, PermissionError, OSError):
        pass
    except Exception:
        pass
    try:
        subprocess.run(cmd, env=env, capture_output=True, timeout=CONVERT_TIMEOUT_S,
                       preexec_fn=_limits())
    except Exception:
        return False
    return os.path.isfile(_first_pdf(out_dir))


def _first_pdf(d: str) -> str:
    for n in os.listdir(d):
        if n.lower().endswith(".pdf"):
            return os.path.join(d, n)
    return os.path.join(d, "out.pdf")


@router.get("/convert", dependencies=[Depends(rate_limit(10, 300))])
async def convert_office(
    uuid: str = Query(...),
    db: Session = Depends(get_db),
    redis: Redis = Depends(get_redis),
    user_id: int = Depends(get_current_user_id),
):
    _require_preview_flag()
    if not is_feature_enabled("enable_preview_office", default=False):
        raise HTTPException(status_code=403, detail="Office 預覽功能尚未啟用")
    batch_ops.assert_not_deleting(redis, uuid)
    f = db.execute(select(File).where(File.uuid == uuid, File.owner_id == user_id)).scalar_one_or_none()
    if f is None or f.deleted_at is not None:
        raise HTTPException(status_code=404, detail="檔案不存在")
    if is_macro_doc(f.name):
        raise HTTPException(status_code=415, detail="含巨集文件基於安全僅供下載，不提供線上預覽")
    if not is_office(f.name):
        raise HTTPException(status_code=404, detail="檔案不存在或非 Office 文件")
    src = os.path.join(settings.STORAGE_BASE_PATH, f.uuid)
    if not os.path.isfile(src):
        raise HTTPException(status_code=404, detail="檔案內容不存在")
    if os.path.getsize(src) > CONVERT_MAX_SRC:
        raise HTTPException(status_code=413, detail="檔案超過 100MB，不轉換預覽")
    mtag = int(f.updated_at.timestamp()) if f.updated_at else 0
    cache_name = f"{uuid}-{mtag}.pdf"
    cache_path = os.path.join(_preview_dir(), cache_name)
    if not os.path.isfile(cache_path):
        if not redis.set(f"conv:{uuid}", "1", nx=True, ex=CONVERT_TIMEOUT_S + 30):
            raise HTTPException(status_code=503, detail="轉換進行中，請稍後重試", headers={"Retry-After": "20"})
        try:
            active = redis.incr("conv:active")
            redis.expire("conv:active", 600)
            if active > 2:
                redis.decr("conv:active")
                raise HTTPException(status_code=503, detail="轉換服務忙碌，請稍後重試", headers={"Retry-After": "30"})
            try:
                soff = _soffice_bin()
                if not soff:
                    raise HTTPException(status_code=501, detail="伺服器未安裝轉換元件")
                with tempfile.TemporaryDirectory(prefix="loconv-") as tmp:
                    out_dir = os.path.join(tmp, "out")
                    prof = os.path.join(tmp, "profile")
                    os.makedirs(out_dir, exist_ok=True)
                    os.makedirs(prof, exist_ok=True)
                    ok = _run_convert(soff, src, out_dir, prof)
                    produced = _first_pdf(out_dir) if ok else ""
                    if not ok or not os.path.isfile(produced):
                        raise HTTPException(status_code=502, detail="轉換失敗，請改用下載")
                    tmp_cache = cache_path + f".tmp{secrets.token_hex(4)}"
                    os.replace(produced, tmp_cache)
                    os.replace(tmp_cache, cache_path)
            finally:
                redis.decr("conv:active")
        finally:
            redis.delete(f"conv:{uuid}")
    return FileResponse(cache_path, media_type="application/pdf",
                        headers={"Cache-Control": "private, max-age=3600",
                                 "X-Content-Type-Options": "nosniff",
                                 "Content-Disposition": "inline"})


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
