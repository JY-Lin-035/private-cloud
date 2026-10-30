"""Admin API for IP / account traffic controls (slow-lane & block ladder).

Privacy policy: full IPs and account ids never leave the server —
list/create responses carry masked IP + numeric rule id; full data lives
only in security.log.
"""
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_admin
from app.config import settings
from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder
from app.constants import Identity
from app.models.ip_control import IpControl
from app.services import security_engine as sec
from app.utils import logger as log
from app.utils.security_log import write_event

router = APIRouter(prefix="/api/ipcontrol", tags=["ipcontrol"])
logger = log.get_logger("ipcontrol_api.log")


def _parse_abs_expires(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail="到期時間格式不正確")
    if dt.tzinfo is not None:
        dt = (dt - dt.utcoffset()).replace(tzinfo=None)
    return dt


class ControlCreate(BaseModel):
    subject_type: str  # ip | ip_token | user
    ip: Optional[str] = None
    token: Optional[str] = None
    username: Optional[str] = None
    action: str = "slow"          # slow | block
    scope: str = "transfer"       # transfer | full
    direction: str = "both"       # up | down | both
    delay_ms: Optional[int] = None
    upload_kbps: Optional[int] = None
    download_kbps: Optional[int] = None
    expires_in_hours: Optional[int] = None  # None = indefinite
    expires_at: Optional[str] = None        # absolute local datetime, beats expires_in_hours
    reason: Optional[str] = None


class ControlUpdate(BaseModel):
    action: Optional[str] = None
    scope: Optional[str] = None
    direction: Optional[str] = None
    delay_ms: Optional[int] = None
    upload_kbps: Optional[int] = None
    download_kbps: Optional[int] = None
    expires_in_hours: Optional[int] = -1  # -1 = keep, null -> set indefinite
    expires_at: Optional[str] = None      # absolute local datetime, beats expires_in_hours
    reason: Optional[str] = None


def _serialize(r: IpControl, actors=None):
    return {
        "id": r.id,
        "subject_type": r.subject_type,
        "ip_masked": sec.mask_ip(r.ip) if r.ip else None,
        "token_prefix": (r.token[:8] if r.token else None),
        "username": r.username,
        "action": r.action,
        "scope": r.scope,
        "direction": r.direction,
        "delay_ms": r.delay_ms,
        "upload_kbps": r.upload_kbps,
        "download_kbps": r.download_kbps,
        "reason": r.reason,
        "auto": bool(r.auto),
        "created_at": r.created_at.isoformat() if r.created_at else None,
        "expires_at": r.expires_at.isoformat() if r.expires_at else None,
        "recent_accounts": actors or [],
    }


def _actors_for(db: Session, ip: Optional[str]):
    if not ip:
        return []
    try:
        from redis import Redis
        r = Redis.from_url(settings.REDIS_URL)
        raw = r.hgetall(f"ipActors:{ip}")
        uids = []
        for k in raw.keys():
            key = k.decode() if isinstance(k, bytes) else k
            try:
                uids.append(int(key))
            except ValueError:
                pass
        if not uids:
            return []
        rows = db.execute(select(Account).where(Account.id.in_(uids))).scalars().all()
        return [a.name for a in rows]
    except Exception:
        return []


@router.get("/admin/list")
async def admin_list(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    rows = db.execute(select(IpControl).order_by(IpControl.id.desc())).scalars().all()
    now = datetime.utcnow()
    out = []
    for r in rows:
        if r.expires_at and r.expires_at <= now:
            continue
        out.append(_serialize(r, _actors_for(db, r.ip)))
    return {"rules": out, "top_scores": sec.get_ip_scores(10)}


@router.post("/admin")
async def admin_create(payload: ControlCreate, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request)
    if payload.subject_type not in ("ip", "ip_token", "user"):
        raise HTTPException(status_code=400, detail="無效的主鍵類型")
    if payload.action not in ("slow", "block") or payload.scope not in ("transfer", "full", "stream"):
        raise HTTPException(status_code=400, detail="無效的動作/範圍")
    if payload.scope == "stream":
        payload.direction = "down"  # playback is downstream-only
    if payload.direction not in ("up", "down", "both"):
        raise HTTPException(status_code=400, detail="無效的方向")

    ip = user_id = username = token = None
    if payload.subject_type in ("ip", "ip_token"):
        ip = (payload.ip or "").strip()
        if not ip or len(ip) > 45 or ("." not in ip and ":" not in ip):
            raise HTTPException(status_code=400, detail="IP 格式不正確")
        if payload.subject_type == "ip_token":
            token = (payload.token or "").strip()
            if len(token) < 8:
                raise HTTPException(status_code=400, detail="需要提供分享連結 token")
    else:
        username = (payload.username or "").strip()
        account = db.execute(select(Account).where(Account.name == username)).scalars().first()
        if not account:
            raise HTTPException(status_code=404, detail="找不到該帳號")
        user_id = account.id

    # one row per (subject, scope): transfer / stream / full are independent knobs
    dup = db.execute(select(IpControl).where(
        IpControl.subject_type == payload.subject_type,
        IpControl.ip == ip, IpControl.token == token, IpControl.user_id == user_id,
        IpControl.scope == payload.scope,
    )).scalars().first()
    if dup:
        raise HTTPException(status_code=400, detail="此對象已有同範圍管控條目，請直接編輯")

    rule = IpControl(
        subject_type=payload.subject_type, ip=ip, token=token, user_id=user_id, username=username,
        action=payload.action, scope=payload.scope, direction=payload.direction,
        delay_ms=payload.delay_ms if payload.delay_ms is not None else settings.SEC_DEFAULT_UPLOAD_DELAY_MS,
        upload_kbps=payload.upload_kbps if payload.upload_kbps is not None else (
            settings.SEC_DEFAULT_UPLOAD_KBPS if payload.direction in ("up", "both") else None),
        download_kbps=payload.download_kbps if payload.download_kbps is not None else (
            settings.SEC_DEFAULT_DOWNLOAD_KBPS if payload.direction in ("down", "both") else None),
        reason=payload.reason, auto=False, created_by=admin.get("id"),
        expires_at=_parse_abs_expires(payload.expires_at) if payload.expires_at else (
            (datetime.utcnow() + timedelta(hours=payload.expires_in_hours)) if payload.expires_in_hours else None),
    )
    if rule.direction == "up":
        rule.download_kbps = None
    elif rule.direction == "down":
        rule.upload_kbps = None
    db.add(rule)
    db.commit()
    sec.invalidate_rules_cache()
    write_event("ipcontrol_create", ip, admin.get("username"), f"rule#{rule.id}",
                f"{payload.subject_type} action={payload.action} scope={payload.scope} dir={payload.direction} reason={payload.reason}")
    return {"id": rule.id}


@router.put("/admin/{rule_id}")
async def admin_update(rule_id: int, payload: ControlUpdate, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request)
    rule = db.get(IpControl, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="管控條目不存在")
    if payload.action is not None:
        if payload.action not in ("slow", "block"):
            raise HTTPException(status_code=400, detail="無效的動作")
        rule.action = payload.action
    if payload.scope is not None:
        if payload.scope not in ("transfer", "full", "stream"):
            raise HTTPException(status_code=400, detail="無效的範圍")
        rule.scope = payload.scope
    if payload.direction is not None:
        if payload.direction not in ("up", "down", "both"):
            raise HTTPException(status_code=400, detail="無效的方向")
        rule.direction = payload.direction
    if payload.delay_ms is not None:
        rule.delay_ms = max(0, min(payload.delay_ms, 30000))
    if payload.upload_kbps is not None:
        rule.upload_kbps = max(16, min(payload.upload_kbps, 1_000_000))
    if payload.download_kbps is not None:
        rule.download_kbps = max(16, min(payload.download_kbps, 1_000_000))
    if payload.expires_at:
        rule.expires_at = _parse_abs_expires(payload.expires_at)
    elif payload.expires_in_hours != -1:
        rule.expires_at = (datetime.utcnow() + timedelta(hours=payload.expires_in_hours)) if payload.expires_in_hours else None
    if payload.reason is not None:
        rule.reason = payload.reason
    if rule.action == "block":
        rule.delay_ms = 0
    # bandwidth must follow the final direction (no stale values)
    if rule.direction == "up":
        rule.download_kbps = None
    elif rule.direction == "down":
        rule.upload_kbps = None
    rule.auto = False  # manual edit takes ownership of an auto rule
    db.commit()
    sec.invalidate_rules_cache()
    write_event("ipcontrol_update", rule.ip, admin.get("username"), f"rule#{rule.id}",
                f"action={rule.action} scope={rule.scope} dir={rule.direction}")
    return {"id": rule.id}


@router.delete("/admin/{rule_id}")
async def admin_delete(rule_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request)
    rule = db.get(IpControl, rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="管控條目不存在")
    db.delete(rule)
    db.commit()
    sec.invalidate_rules_cache()
    write_event("ipcontrol_delete", rule.ip, admin.get("username"), f"rule#{rule.id}", "解除管控")
    return {"deleted": rule_id}


class SuspendRequest(BaseModel):
    username: str


@router.post("/admin/suspend")
async def admin_suspend_account(payload: SuspendRequest, request: Request, db: Session = Depends(get_db)):
    """小黑屋 + 踢出 session（IP 管控頁的帳號處置台階）."""
    admin = require_admin(request)
    account = db.execute(select(Account).where(Account.name == payload.username.strip())).scalars().first()
    if not account:
        raise HTTPException(status_code=404, detail="找不到該帳號")
    if account.identity == Identity.ADMIN:
        raise HTTPException(status_code=403, detail="不能停用其他管理員")
    account.enable = False
    db.commit()
    try:
        from redis import Redis
        r = Redis.from_url(settings.REDIS_URL)
        r.delete(f"session:{account.id}")
        r.delete(f"session_data:{account.id}")
    except Exception:
        pass
    try:
        from app.services import collab_events
        collab_events.revoke_user(account.id, "account suspended")
    except Exception:
        pass
    write_event("account_suspend", None, admin.get("username"), account.name, "由 IP Management 停用")
    return {"suspended": account.name}


@router.get("/admin/hotlinks")
async def admin_hotlinks(request: Request, ip: str = Query(..., max_length=45), db: Session = Depends(get_db)):
    """Recent share links an IP has been hammering (for one-click ip_token rule creation)."""
    require_admin(request)
    try:
        from redis import Redis
        raw = Redis.from_url(settings.REDIS_URL).hgetall(f"hotlinks:{ip}")
    except Exception:
        raw = {}
    links = []
    for v in (raw or {}).values():
        token = v.decode() if isinstance(v, bytes) else str(v)
        f = db.execute(select(File).where(File.shared == token)).scalars().first()
        if f:
            owner = db.get(Account, f.owner_id)
            links.append({"token": token, "item": f.name, "type": "file", "owner": owner.name if owner else "?"})
            continue
        d = db.execute(select(Folder).where(Folder.shared == token)).scalars().first()
        if d:
            owner = db.get(Account, d.owner_id)
            links.append({"token": token, "item": d.name, "type": "folder", "owner": owner.name if owner else "?"})
    return {"links": links}
