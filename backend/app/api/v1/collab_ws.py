import os
from typing import Dict, Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from app.database import SessionLocal
from app.config import settings
from app.repositories.file_repository import FileRepository
from app.repositories.collaboration_repository import CollaborationRepository

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


def _get_file_path(file_uuid: str) -> Optional[str]:
    db = SessionLocal()
    try:
        file_repo = FileRepository(db)
        file = file_repo.get_by_uuid(file_uuid)
        if not file:
            return None
        base = settings.STORAGE_BASE_PATH
        if not os.path.isabs(base):
            base = os.path.join(os.getcwd(), base)
        return os.path.join(base, file.uuid)
    finally:
        db.close()


def _load_file_content(file_uuid: str) -> str:
    file_path = _get_file_path(file_uuid)
    if not file_path or not os.path.exists(file_path):
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return ""


def _save_file_content(file_uuid: str, content: str):
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
    await websocket.accept()

    if file_uuid not in rooms:
        rooms[file_uuid] = {}
    rooms[file_uuid][user_id] = websocket

    content = _load_file_content(file_uuid)
    await websocket.send_json({
        "type": "load_file",
        "content": content,
        "users": list(rooms[file_uuid].keys())
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
                await _broadcast(file_uuid, {
                    "type": "update",
                    "user_id": user_id,
                    "content": data.get("content")
                }, exclude=user_id)

            elif msg_type == "save":
                _save_file_content(file_uuid, data.get("content", ""))

            elif msg_type == "cursor":
                await _broadcast(file_uuid, {
                    "type": "cursor",
                    "user_id": user_id,
                    "cursor": data.get("cursor")
                }, exclude=user_id)

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