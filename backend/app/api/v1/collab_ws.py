import os
import base64
from typing import Any, Dict, Optional
from uuid import uuid4
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from redis import Redis
from app.database import SessionLocal
from app.config import settings
from app.repositories.file_repository import FileRepository
from app.repositories.collaboration_repository import CollaborationRepository
from app.services.snapshot_service import (
    get_snapshots, switch_to_snapshot, save_snapshot,
    _get_content_key, _get_file_path
)

router = APIRouter()

rooms: Dict[str, Dict[str, Dict[str, Any]]] = {}
MAX_Y_UPDATES = 1000
Y_STATE_VERSION = "4"


def _room_users(file_uuid: str) -> list[int]:
    if file_uuid not in rooms:
        return []
    return sorted({connection["user_id"] for connection in rooms[file_uuid].values()})


async def _broadcast(file_uuid: str, message: dict, exclude: Optional[str] = None):
    if file_uuid not in rooms:
        return
    for connection_id, connection in list(rooms[file_uuid].items()):
        if connection_id != exclude:
            try:
                await connection["websocket"].send_json(message)
            except Exception:
                pass


def _load_file_content(file_uuid: str, redis: Redis) -> str:
    """Load content from Redis cache first, then fall back to file system."""
    cached = redis.get(f"collab_content:{file_uuid}")
    if cached:
        return cached
    file_path = _get_file_path(file_uuid)
    if not file_path or not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            redis.set(f"collab_content:{file_uuid}", content)
            return content
    except Exception:
        return ""


def _set_collab_content(redis: Redis, file_uuid: str, content: Optional[str]) -> bool:
    if content is None:
        return False
    existing = redis.get(f"collab_content:{file_uuid}") or ""
    if not content.strip() and existing.strip():
        return False
    redis.set(f"collab_content:{file_uuid}", content)
    return True


def _snapshot_summary(snapshots: list[dict]) -> list[dict]:
    return [{"id": str(s["id"]), "timestamp": s["timestamp"]} for s in snapshots]


def _save_file_content(file_uuid: str, content: str):
    """Save content to file system."""
    file_path = _get_file_path(file_uuid)
    if not file_path:
        return
    try:
        if not content.strip() and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
            return
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


def _get_y_updates_key(file_uuid: str) -> str:
    return f"collab_yupdates:{file_uuid}"


def _get_y_base_key(file_uuid: str) -> str:
    return f"collab_ybase:{file_uuid}"


def _get_y_version_key(file_uuid: str) -> str:
    return f"collab_yversion:{file_uuid}"


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


def _append_y_update(file_uuid: str, redis: Redis, update: str) -> None:
    base64.b64decode(update, validate=True)
    key = _get_y_updates_key(file_uuid)
    redis.rpush(key, update)
    redis.ltrim(key, -MAX_Y_UPDATES, -1)


def _reset_y_state(file_uuid: str, redis: Redis, content: str) -> None:
    redis.set(_get_y_base_key(file_uuid), content)
    redis.set(_get_y_version_key(file_uuid), Y_STATE_VERSION)
    redis.delete(_get_y_updates_key(file_uuid))


def _check_permission(file_uuid: str, user_id: int) -> bool:
    db = SessionLocal()
    try:
        file_repo = FileRepository(db)
        collab_repo = CollaborationRepository(db)
        file = file_repo.get_by_uuid(file_uuid)
        if not file:
            return False
        if file.owner_id == user_id:
            return True
        collab = collab_repo.get_by_file_and_collaborator(file_uuid, user_id)
        return collab is not None
    except Exception:
        return False
    finally:
        db.close()


@router.websocket("/ws/collab/{file_uuid}")
async def websocket_collab(
    websocket: WebSocket,
    file_uuid: str,
    user_id: int = Query(...)
):
    # Create Redis connection directly (Depends doesn't work well with WebSocket)
    redis = Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5,
        retry_on_timeout=True
    )
    await websocket.accept()

    if file_uuid not in rooms:
        rooms[file_uuid] = {}
    connection_id = str(uuid4())
    rooms[file_uuid][connection_id] = {
        "user_id": user_id,
        "websocket": websocket
    }

    _ensure_y_state_version(file_uuid, redis)
    content = _load_y_base_content(file_uuid, redis)
    y_updates = _get_y_updates(file_uuid, redis)
    # Get snapshots list
    snapshots = get_snapshots(file_uuid, redis)

    await websocket.send_json({
        "type": "load_file",
        "content": content,
        "y_updates": y_updates,
        "needs_y_init": len(y_updates) == 0 and len(rooms[file_uuid]) == 1,
        "users": _room_users(file_uuid),
        "snapshots": _snapshot_summary(snapshots)
    })

    await _broadcast(file_uuid, {
        "type": "users",
        "users": _room_users(file_uuid)
    }, exclude=connection_id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "y_init_state":
                update = data.get("update")
                content = data.get("content")
                if update and not _has_y_updates(file_uuid, redis):
                    _append_y_update(file_uuid, redis, update)
                    _set_collab_content(redis, file_uuid, content)
                    await _broadcast(file_uuid, {
                        "type": "y_init_state",
                        "user_id": user_id,
                        "update": update
                    }, exclude=connection_id)

            elif msg_type == "y_update":
                update = data.get("update")
                if update:
                    _append_y_update(file_uuid, redis, update)
                    await _broadcast(file_uuid, {
                        "type": "y_update",
                        "user_id": user_id,
                        "update": update
                    }, exclude=connection_id)

            elif msg_type == "y_projection":
                _set_collab_content(redis, file_uuid, data.get("content"))

            elif msg_type in ("persist_text", "save"):
                content = data.get("content", "")
                if _set_collab_content(redis, file_uuid, content):
                    _save_file_content(file_uuid, content)
                    if data.get("create_snapshot"):
                        save_snapshot(file_uuid, redis)
                        snapshots = get_snapshots(file_uuid, redis)
                        await websocket.send_json({
                            "type": "snapshots",
                            "snapshots": _snapshot_summary(snapshots)
                        })

            elif msg_type == "cursor":
                await _broadcast(file_uuid, {
                    "type": "cursor",
                    "user_id": user_id,
                    "cursor": data.get("cursor")
                }, exclude=connection_id)

            elif msg_type == "get_snapshots":
                snapshots = get_snapshots(file_uuid, redis)
                await websocket.send_json({
                    "type": "snapshots",
                    "snapshots": _snapshot_summary(snapshots)
                })

            elif msg_type == "switch_version":
                snapshot_id = data.get("version_id")
                if snapshot_id:
                    content = switch_to_snapshot(file_uuid, snapshot_id, redis)
                    if content is not None:
                        redis.set(f"collab_content:{file_uuid}", content)
                        _save_file_content(file_uuid, content)
                        snapshots = get_snapshots(file_uuid, redis)
                        await websocket.send_json({
                            "type": "apply_version",
                            "content": content,
                            "version_id": snapshot_id,
                            "snapshots": _snapshot_summary(snapshots)
                        })
                    else:
                        await websocket.send_json({
                            "type": "switch_version_failed",
                            "version_id": snapshot_id,
                            "message": "找不到指定版本"
                        })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if file_uuid in rooms and connection_id in rooms[file_uuid]:
            del rooms[file_uuid][connection_id]
            if not rooms[file_uuid]:
                del rooms[file_uuid]
        await _broadcast(file_uuid, {
            "type": "users",
            "users": _room_users(file_uuid)
        })
