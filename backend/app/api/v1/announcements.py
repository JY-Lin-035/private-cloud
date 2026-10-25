from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db, require_admin, get_current_user_id
from app.models.announcement import Announcement
from app.utils import logger as log

router = APIRouter(prefix="/api/announcements", tags=["announcements"])
logger = log.get_logger("announcements_api.log")

MAX_ACTIVE = 20
MAX_LEN = 500


def _clean_content(raw: str) -> str:
    text = (raw or '').replace('\r', ' ').replace('\n', ' ')
    text = ''.join(ch for ch in text if ch >= ' ' or ch == ' ')
    return text.strip()


def _is_effective(a: Announcement, now: datetime) -> bool:
    return bool(a.enabled) and (a.expires_at is None or a.expires_at > now)


def _parse_expires(value: Optional[str]) -> Optional[datetime]:
    """Accept ISO datetime (with or without tz) and store naive UTC."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        raise HTTPException(status_code=400, detail='到期時間格式不正確')
    if dt.tzinfo is not None:
        dt = (dt - dt.utcoffset()).replace(tzinfo=None)  # store naive UTC
    return dt


class AnnouncementCreate(BaseModel):
    content: str
    expires_at: Optional[str] = None
    enabled: bool = True


class AnnouncementUpdate(BaseModel):
    content: Optional[str] = None
    expires_at: Optional[str] = None  # "" clears -> indefinite
    enabled: Optional[bool] = None


@router.get("")
async def active_announcements(db: Session = Depends(get_db), user_id: int = Depends(get_current_user_id)):
    """Any signed-in user: contents currently shown in the nav ticker."""
    now = datetime.utcnow()
    rows = db.execute(
        select(Announcement).where(Announcement.enabled.is_(True)).order_by(Announcement.created_at.desc())
    ).scalars().all()
    return {'announcements': [a.content for a in rows if _is_effective(a, now)]}


@router.get("/admin/list")
async def admin_list(request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    now = datetime.utcnow()
    rows = db.execute(select(Announcement).order_by(Announcement.created_at.desc())).scalars().all()
    return {'announcements': [{
        'id': a.id,
        'content': a.content,
        'enabled': bool(a.enabled),
        'effective': _is_effective(a, now),
        'expired': bool(a.expires_at and a.expires_at <= now),
        'expires_at': a.expires_at.isoformat() if a.expires_at else None,
        'created_at': a.created_at.isoformat() if a.created_at else None,
    } for a in rows]}


@router.post("/admin")
async def admin_create(request_: AnnouncementCreate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    content = _clean_content(request_.content)
    if not content or len(content) > MAX_LEN:
        raise HTTPException(status_code=400, detail=f'公告內容需為 1-{MAX_LEN} 字')
    now = datetime.utcnow()
    active = db.execute(select(Announcement).where(Announcement.enabled.is_(True))).scalars().all()
    if sum(1 for a in active if _is_effective(a, now)) >= MAX_ACTIVE:
        raise HTTPException(status_code=400, detail=f'生效中的公告最多 {MAX_ACTIVE} 條')
    a = Announcement(content=content, enabled=request_.enabled, expires_at=_parse_expires(request_.expires_at))
    db.add(a)
    db.commit()
    admin = require_admin(request)
    logger.info(f"Announcement created id={a.id} by admin_user_id={admin.get('id')}")
    return {'id': a.id}


@router.put("/admin/{item_id}")
async def admin_update(item_id: int, payload: AnnouncementUpdate, request: Request, db: Session = Depends(get_db)):
    require_admin(request)
    a = db.get(Announcement, item_id)
    if not a:
        raise HTTPException(status_code=404, detail='公告不存在')
    if payload.content is not None:
        content = _clean_content(payload.content)
        if not content or len(content) > MAX_LEN:
            raise HTTPException(status_code=400, detail=f'公告內容需為 1-{MAX_LEN} 字')
        a.content = content
    if payload.enabled is not None:
        a.enabled = payload.enabled
    if payload.expires_at is not None:
        a.expires_at = _parse_expires(payload.expires_at or None)
    db.commit()
    admin = require_admin(request)
    logger.info(f"Announcement updated id={item_id} by admin_user_id={admin.get('id')}")
    return {'id': a.id}


@router.delete("/admin/{item_id}")
async def admin_delete(item_id: int, request: Request, db: Session = Depends(get_db)):
    admin = require_admin(request)
    a = db.get(Announcement, item_id)
    if not a:
        raise HTTPException(status_code=404, detail='公告不存在')
    db.delete(a)
    db.commit()
    logger.info(f"Announcement deleted id={item_id} by admin_user_id={admin.get('id')}")
    return {'deleted': item_id}
