import os
import re
import time
import base64
import asyncio
import threading
from typing import Any, Dict, Optional
from uuid import uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from redis import Redis
from sqlalchemy import select

from app.database import SessionLocal
from app.config import settings
from app.repositories.file_repository import FileRepository
from app.repositories.collaboration_repository import CollaborationRepository
from app.models.file import File
from app.services import collab_events
from app.services.snapshot_service import (
    get_snapshots, switch_to_snapshot, save_snapshot, _get_content_key,
)
from app.services.collab_persist import persist_content, content_size_ok
from app.utils import logger as log

router = APIRouter()
logger = log.get_logger("collab_ws.log")

WS_SUBPROTOCOL = settings.WS_SUBPROTOCOL
_TICKET_RE = re.compile(r"^[A-Za-z0-9_-]{43}$")
MAX_Y_UPDATES = 1000
Y_STATE_VERSION = "5"
PERM_TTL = 10  # seconds; per-connection permission cache

_perm_cache: Dict[tuple[str, int], tuple[bool, float]] = {}
_perm_lock = threading.Lock()


# ---------------------------------------------------------------- rooms

class RoomManager:
    def __init__(self) -> None:
        self.rooms: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def add(self, file_uuid: str, connection_id: str, user_id: int, websocket: WebSocket) -> None:
        self.rooms.setdefault(file_uuid, {})[connection_id] = {
            "user_id": user_id,
            "websocket": websocket,
        }

    def remove(self, file_uuid: str, connection_id: str) -> None:
        conns = self.rooms.get(file_uuid)
        if not conns:
            return
        conns.pop(connection_id, None)
        if not conns:
            self.rooms.pop(file_uuid, None)

    def users(self, file_uuid: str) -> list[int]:
        conns = self.rooms.get(file_uuid) or {}
        return sorted({c["user_id"] for c in conns.values()})

    def count(self, file_uuid: str) -> int:
        return len(self.rooms.get(file_uuid) or {})

    async def close_where(self, *, file_uuid: Optional[str] = None,
                          user_id: Optional[int] = None, code: int = 4403) -> None:
        targets = []
        for fu, conns in list(self.rooms.items()):
            if file_uuid is not None and fu != file_uuid:
                continue
            for cid, conn in list(conns.items()):
                if user_id is not None and conn["user_id"] != user_id:
                    continue
                targets.append((fu, cid, conn["websocket"]))
        for fu, cid, ws in targets:
            self.remove(fu, cid)
            try:
                await ws.close(code=code)
            except Exception:
                pass


manager = RoomManager()


async def _kick(kind: Optional[str], file_uuid: Optional[str],
                user_id: Optional[int], reason: str = "") -> None:
    if kind == "file" and file_uuid:
        await manager.close_where(file_uuid=file_uuid)
    elif kind == "file_user" and file_uuid and user_id is not None:
        await manager.close_where(file_uuid=file_uuid, user_id=int(user_id))
    elif kind == "user" and user_id is not None:
        await manager.close_where(user_id=int(user_id))


collab_events.set_kicker(_kick)


# ---------------------------------------------------------------- helpers

def _room_users(file_uuid: str) -> list[int]:
    return manager.users(file_uuid)


async def _broadcast(file_uuid: str, message: dict, exclude: Optional[str] = None):
    conns = manager.rooms.get(file_uuid) or {}
    for connection_id, connection in list(conns.items()):
        if connection_id != exclude:
            try:
                await connection["websocket"].send_json(message)
            except Exception:
                pass


def _load_file_content(file_uuid: str, redis: Redis) -> str:
    cached = redis.get(f"collab_content:{file_uuid}")
    if cached:
        return cached
    from app.services.snapshot_service import _get_file_path
    file_path = _get_file_path(file_uuid)
    if not file_path or not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            _set_collab_content(redis, file_uuid, content)
            return content
    except Exception:
        return ""


def _set_collab_content(redis: Redis, file_uuid: str, content: Optional[str]) -> bool:
    if content is None:
        return False
    existing = redis.get(f"collab_content:{file_uuid}") or ""
    if not content.strip() and existing.strip():
        return False
    key = f"collab_content:{file_uuid}"
    redis.set(key, content)
    try:
        redis.expire(key, settings.COLLAB_STATE_TTL_SECONDS)
    except Exception:
        pass
    return True


def _snapshot_summary(snapshots: list[dict]) -> list[dict]:
    return [{"id": str(s["id"]), "timestamp": s["timestamp"]} for s in snapshots]


def _set_y_state(redis: Redis, file_uuid: str, update: str) -> None:
    key = _get_y_state_key(file_uuid)
    redis.set(key, update)
    try:
        redis.expire(key, settings.COLLAB_STATE_TTL_SECONDS)
    except Exception:
        pass


def _get_y_updates_key(file_uuid: str) -> str:
    return f"collab_yupdates:{file_uuid}"


def _get_y_base_key(file_uuid: str) -> str:
    return f"collab_ybase:{file_uuid}"


def _get_y_version_key(file_uuid: str) -> str:
    return f"collab_yversion:{file_uuid}"


def _get_y_state_key(file_uuid: str) -> str:
    return f"collab_ystate:{file_uuid}"


def _ensure_y_state_version(file_uuid: str, redis: Redis) -> None:
    if redis.get(_get_y_version_key(file_uuid)) == Y_STATE_VERSION:
        return
    content = _load_file_content(file_uuid, redis)
    _reset_y_state(file_uuid, redis, content)


def _load_y_base_content(file_uuid: str, redis: Redis) -> str:
    base = redis.get(_get_y_base_key(file_uuid))
    if base is not None:
        return base
    content = _load_file_content(file_uuid, redis)
    redis.set(_get_y_base_key(file_uuid), content)
    return content


def _get_y_updates(file_uuid: str, redis: Redis) -> list[str]:
    return redis.lrange(_get_y_updates_key(file_uuid), 0, -1)


def _has_y_updates(file_uuid: str, redis: Redis) -> bool:
    return redis.llen(_get_y_updates_key(file_uuid)) > 0


def _b64_len(value: Any) -> Optional[int]:
    """Validate base64 and return decoded byte length (None if invalid/oversize)."""
    if not isinstance(value, str) or len(value) > (settings.MAX_Y_UPDATE_BYTES * 4 // 3) + 8:
        return None
    try:
        return len(base64.b64decode(value, validate=True))
    except Exception:
        return None


def _append_y_update(file_uuid: str, redis: Redis, update: str,
                     max_bytes: Optional[int] = None) -> bool:
    length = _b64_len(update)
    limit = max_bytes if max_bytes is not None else settings.MAX_Y_UPDATE_BYTES
    if length is None or length > limit:
        return False
    key = _get_y_updates_key(file_uuid)
    redis.rpush(key, update)
    redis.ltrim(key, -MAX_Y_UPDATES, -1)
    try:
        redis.expire(key, settings.COLLAB_STATE_TTL_SECONDS)
        bytes_key = f"collab_ybytes:{file_uuid}"
        total = redis.incrby(bytes_key, length)
        redis.expire(bytes_key, settings.COLLAB_STATE_TTL_SECONDS)
        # Bound per-file update log growth. Client projections keep y_state fresh,
        # so dropping the incremental log only forces a state-based resync.
        if total > settings.COLLAB_UPDATE_BUDGET_BYTES:
            redis.delete(key)
            redis.set(bytes_key, 0)
            redis.expire(bytes_key, settings.COLLAB_STATE_TTL_SECONDS)
    except Exception:
        pass
    return True


def _reset_y_state(file_uuid: str, redis: Redis, content: str) -> None:
    base = _get_y_base_key(file_uuid)
    ver = _get_y_version_key(file_uuid)
    redis.set(base, content)
    redis.set(ver, Y_STATE_VERSION)
    for k in (base, ver):
        try:
            redis.expire(k, settings.COLLAB_STATE_TTL_SECONDS)
        except Exception:
            pass
    redis.delete(_get_y_updates_key(file_uuid))
    redis.delete(_get_y_state_key(file_uuid))
    redis.delete(f"collab_ybytes:{file_uuid}")


def _check_permission(file_uuid: str, user_id: int) -> bool:
    db = SessionLocal()
    try:
        file = FileRepository(db).get_by_uuid(file_uuid)
        if not file or file.deleted_at is not None:
            return False
        if file.owner_id == user_id:
            return True
        return CollaborationRepository(db).get_by_file_and_collaborator(file_uuid, user_id) is not None
    except Exception:
        return False
    finally:
        db.close()


def _perm_ok(file_uuid: str, user_id: int, force: bool = False) -> bool:
    key = (file_uuid, user_id)
    now = time.time()
    with _perm_lock:
        cached = _perm_cache.get(key)
        if cached and not force and now - cached[1] < PERM_TTL:
            return cached[0]
    ok = _check_permission(file_uuid, user_id)
    with _perm_lock:
        if len(_perm_cache) > 10000:
            _perm_cache.clear()
        _perm_cache[key] = (ok, now)
    return ok


def _session_alive(redis: Redis, user_id: int) -> bool:
    try:
        return bool(redis.get(f"session:{user_id}"))
    except Exception:
        return False


async def _watch(websocket: WebSocket, file_uuid: str, user_id: int,
                 redis: Redis, stop: asyncio.Event) -> None:
    """Close the socket if the session dies or access is revoked."""
    while True:
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
            return
        except asyncio.TimeoutError:
            pass
        alive = await asyncio.to_thread(_session_alive, redis, user_id)
        if not alive:
            try:
                await websocket.close(code=4401)
            except Exception:
                pass
            return
        if not await asyncio.to_thread(_perm_ok, file_uuid, user_id, True):
            try:
                await websocket.close(code=4403)
            except Exception:
                pass
            return


# ---------------------------------------------------------------- endpoint

@router.websocket("/ws/collab/{file_uuid}")
async def websocket_collab(websocket: WebSocket, file_uuid: str):
    redis = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True,
    )

    try:
        async def _reject(code: int) -> None:
            try:
                await websocket.close(code=code)
            except Exception:
                pass
            try:
                await redis.close()
            except Exception:
                pass

        origin = websocket.headers.get("origin")
        if origin and origin.rstrip("/") not in settings.allowed_origins:
            await _reject(4403)
            return

        offered = list(websocket.scope.get("subprotocols") or [])
        if WS_SUBPROTOCOL not in offered:
            await _reject(4401)
            return
        candidates = [p for p in offered if p != WS_SUBPROTOCOL]
        if len(candidates) != 1 or not _TICKET_RE.fullmatch(candidates[0]):
            await _reject(4401)
            return

        try:
            raw = redis.getdel(f"wsTicket:{candidates[0]}")
        except Exception:
            raw = None
        if not raw:
            await _reject(4401)
            return
        try:
            uid_s, ticketed_file = raw.split(":", 1)
            user_id = int(uid_s)
        except (ValueError, AttributeError):
            await _reject(4401)
            return
        if ticketed_file != file_uuid:
            await _reject(4403)
            return
        # A logout between ticket issuance and handshake must not connect.
        try:
            if not redis.get(f"session:{user_id}"):
                await _reject(4401)
                return
        except Exception:
            await _reject(4401)
            return
        if not await asyncio.to_thread(_perm_ok, file_uuid, user_id, True):
            await _reject(4403)
            return
        if manager.count(file_uuid) >= settings.MAX_ROOM_CONNECTIONS:
            await _reject(4429)
            return

        await websocket.accept(subprotocol=WS_SUBPROTOCOL)
    except Exception:
        try:
            await redis.close()
        except Exception:
            pass
        return

    connection_id = str(uuid4())
    manager.add(file_uuid, connection_id, user_id, websocket)
    logger.info(f"Collab WS connected file={file_uuid} user={user_id}")

    try:
        await asyncio.to_thread(_ensure_y_state_version, file_uuid, redis)
        content = await asyncio.to_thread(_load_y_base_content, file_uuid, redis)
        y_state = redis.get(_get_y_state_key(file_uuid))
        y_updates = _get_y_updates(file_uuid, redis)
        snapshots = get_snapshots(file_uuid, redis)

        await websocket.send_json({
            "type": "load_file",
            "content": content,
            "y_state": y_state,
            "y_updates": y_updates,
            "needs_y_init": len(y_updates) == 0 and len(manager.rooms.get(file_uuid, {})) == 1,
            "users": _room_users(file_uuid),
            "snapshots": _snapshot_summary(snapshots),
        })

        await _broadcast(file_uuid, {
            "type": "users",
            "users": _room_users(file_uuid),
        }, exclude=connection_id)

        stop = asyncio.Event()
        watcher = asyncio.create_task(_watch(websocket, file_uuid, user_id, redis, stop))
        window_start = time.monotonic()
        msg_count = 0

        while True:
            data = await websocket.receive_json()
            msg_count += 1
            if time.monotonic() - window_start > 60:
                window_start = time.monotonic()
                msg_count = 0
            if msg_count > settings.WS_MSG_PER_MIN:
                await websocket.close(code=4429)
                break

            msg_type = data.get("type") if isinstance(data, dict) else None

            if msg_type == "y_init_state":
                if not await asyncio.to_thread(_perm_ok, file_uuid, user_id):
                    await websocket.close(code=4403)
                    break
                update = data.get("update")
                content = data.get("content")
                if update and not _has_y_updates(file_uuid, redis):
                    if not _append_y_update(file_uuid, redis, update, settings.MAX_Y_UPDATE_BYTES):
                        continue
                    if content is not None and content_size_ok(content):
                        _set_collab_content(redis, file_uuid, content)
                    _set_y_state(redis, file_uuid, update)
                    await _broadcast(file_uuid, {
                        "type": "y_init_state",
                        "user_id": user_id,
                        "update": update,
                    }, exclude=connection_id)

            elif msg_type == "y_update":
                if not await asyncio.to_thread(_perm_ok, file_uuid, user_id):
                    await websocket.close(code=4403)
                    break
                update = data.get("update")
                if update and _append_y_update(file_uuid, redis, update, settings.MAX_Y_INCREMENTAL_BYTES):
                    await _broadcast(file_uuid, {
                        "type": "y_update",
                        "user_id": user_id,
                        "update": update,
                    }, exclude=connection_id)

            elif msg_type == "y_projection":
                if not await asyncio.to_thread(_perm_ok, file_uuid, user_id):
                    await websocket.close(code=4403)
                    break
                content = data.get("content")
                if content is not None and content_size_ok(content):
                    _set_collab_content(redis, file_uuid, content)
                state_update = data.get("state_update")
                if state_update:
                    length = _b64_len(state_update)
                    if length is not None and length <= settings.MAX_Y_UPDATE_BYTES:
                        _set_y_state(redis, file_uuid, state_update)

            elif msg_type in ("persist_text", "save"):
                # Disk-touching op: never trust the 10s permission cache.
                if not await asyncio.to_thread(_perm_ok, file_uuid, user_id, True):
                    await websocket.close(code=4403)
                    break
                content = data.get("content", "")
                if not content_size_ok(content):
                    await websocket.send_json({"type": "save_error", "message": "內容超過大小上限"})
                    continue
                if _set_collab_content(redis, file_uuid, content):
                    ok = await asyncio.to_thread(persist_content, file_uuid, content)
                    if not ok:
                        await websocket.send_json({"type": "save_error", "message": "儲存失敗或超過配額"})
                    elif data.get("create_snapshot"):
                        await asyncio.to_thread(save_snapshot, file_uuid, redis)
                        snapshots = await asyncio.to_thread(get_snapshots, file_uuid, redis)
                        await websocket.send_json({
                            "type": "snapshots",
                            "snapshots": _snapshot_summary(snapshots),
                        })

            elif msg_type == "cursor":
                await _broadcast(file_uuid, {
                    "type": "cursor",
                    "user_id": user_id,
                    "cursor": data.get("cursor"),
                }, exclude=connection_id)

            elif msg_type == "get_snapshots":
                snapshots = get_snapshots(file_uuid, redis)
                await websocket.send_json({
                    "type": "snapshots",
                    "snapshots": _snapshot_summary(snapshots),
                })

            elif msg_type == "switch_version":
                # Disk-touching op: never trust the 10s permission cache.
                if not await asyncio.to_thread(_perm_ok, file_uuid, user_id, True):
                    await websocket.close(code=4403)
                    break
                snapshot_id = data.get("version_id")
                if snapshot_id:
                    prev_content = redis.get(_get_content_key(file_uuid))
                    content = await asyncio.to_thread(switch_to_snapshot, file_uuid, snapshot_id, redis)
                    if content is not None and content_size_ok(content):
                        _set_collab_content(redis, file_uuid, content)
                        if not await asyncio.to_thread(persist_content, file_uuid, content):
                            # Disk write failed (quota/size/gone): roll the
                            # Redis view back so it never diverges from disk.
                            if prev_content is not None:
                                _set_collab_content(redis, file_uuid, prev_content)
                            await websocket.send_json({
                                "type": "switch_version_failed",
                                "version_id": snapshot_id,
                                "message": "無法切換：配額不足或檔案已移除",
                            })
                            continue
                        snapshots = get_snapshots(file_uuid, redis)
                        await websocket.send_json({
                            "type": "apply_version",
                            "content": content,
                            "version_id": snapshot_id,
                            "snapshots": _snapshot_summary(snapshots),
                        })
                    else:
                        await websocket.send_json({
                            "type": "switch_version_failed",
                            "version_id": snapshot_id,
                            "message": "找不到指定版本或內容過大",
                        })

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.info(f"Collab WS error file={file_uuid} user={user_id}: {e}")
    finally:
        try:
            stop.set()
            watcher.cancel()
        except Exception:
            pass
        manager.remove(file_uuid, connection_id)
        await _broadcast(file_uuid, {
            "type": "users",
            "users": _room_users(file_uuid),
        })
        try:
            await redis.close()
        except Exception:
            pass