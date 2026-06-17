import os
import json
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from redis import Redis
from app.database import SessionLocal
from app.config import settings
from app.repositories.file_repository import FileRepository
from app.repositories.collaboration_repository import CollaborationRepository
from app.services.snapshot_service import (
    get_snapshots, switch_to_snapshot,
    _get_content_key, _get_file_path
)

router = APIRouter()

rooms: Dict[str, Dict[int, WebSocket]] = {}


async def _broadcast(file_uuid: str, message: dict, exclude: Optional[int] = None):
    if file_uuid not in rooms:
        return
    for uid, ws in rooms[file_uuid].items():
        if uid != exclude:
            try:
                await ws.send_json(message)
            except Exception:
                pass


def _load_file_content(file_uuid: str, redis: Redis) -> str:
    """Load content from Redis cache first, then fall back to file system."""
    cached = redis.get(f"collab_content:{file_uuid}")
    if cached is not None:
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


def _save_file_content(file_uuid: str, content: str):
    """Save content to file system."""
    file_path = _get_file_path(file_uuid)
    if not file_path:
        return
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass


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
    rooms[file_uuid][user_id] = websocket

    # Load content from Redis or file system
    content = _load_file_content(file_uuid, redis)
    # Get snapshots list
    snapshots = get_snapshots(file_uuid, redis)

    await websocket.send_json({
        "type": "load_file",
        "content": content,
        "users": list(rooms[file_uuid].keys()),
        "snapshots": [{"id": s["id"], "timestamp": s["timestamp"]} for s in snapshots]
    })

    await _broadcast(file_uuid, {
        "type": "user_joined",
        "user_id": user_id
    }, exclude=user_id)

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")

            if msg_type == "update":
                content = data.get("content")
                if content is not None:
                    # Save to Redis immediately
                    redis.set(f"collab_content:{file_uuid}", content)
                await _broadcast(file_uuid, {
                    "type": "update",
                    "user_id": user_id,
                    "content": content
                }, exclude=user_id)

            elif msg_type == "save":
                content = data.get("content", "")
                if content:
                    redis.set(f"collab_content:{file_uuid}", content)
                _save_file_content(file_uuid, content)

            elif msg_type == "cursor":
                await _broadcast(file_uuid, {
                    "type": "cursor",
                    "user_id": user_id,
                    "cursor": data.get("cursor")
                }, exclude=user_id)

            elif msg_type == "switch_version":
                snapshot_id = data.get("version_id")
                if snapshot_id:
                    content = switch_to_snapshot(file_uuid, snapshot_id, redis)
                    if content is not None:
                        await websocket.send_json({
                            "type": "load_version",
                            "content": content,
                            "version_id": snapshot_id
                        })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        if file_uuid in rooms and user_id in rooms[file_uuid]:
            del rooms[file_uuid][user_id]
            if not rooms[file_uuid]:
                del rooms[file_uuid]
        await _broadcast(file_uuid, {
            "type": "user_left",
            "user_id": user_id
        })