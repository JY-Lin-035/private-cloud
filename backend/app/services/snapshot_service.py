import os
import json
import time
from datetime import datetime
from typing import Optional, List, Dict
from redis import Redis
from app.database import SessionLocal
from app.config import settings
from app.repositories.file_repository import FileRepository

SNAPSHOT_PREFIX = "collab_snapshot:"
CONTENT_PREFIX = "collab_content:"
MAX_SNAPSHOTS = 3
SNAPSHOT_INTERVAL = 900  # 15 minutes in seconds
AUTO_SAVE_INTERVAL = 30  # 30 seconds


def _get_snapshot_key(file_uuid: str) -> str:
    return f"{SNAPSHOT_PREFIX}{file_uuid}"


def _get_content_key(file_uuid: str) -> str:
    return f"{CONTENT_PREFIX}{file_uuid}"


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


def save_snapshot(file_uuid: str, redis: Redis):
    """Save current content as a snapshot (called every 15 minutes)."""
    content = redis.get(_get_content_key(file_uuid))
    if not content:
        return

    snapshots = get_snapshots(file_uuid, redis)

    # Add new snapshot
    new_snapshot = {
        "id": int(time.time()),
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    snapshots.append(new_snapshot)

    # Keep only the latest MAX_SNAPSHOTS
    if len(snapshots) > MAX_SNAPSHOTS:
        snapshots = snapshots[-MAX_SNAPSHOTS:]

    redis.set(_get_snapshot_key(file_uuid), json.dumps(snapshots))


def get_snapshots(file_uuid: str, redis: Redis) -> List[Dict]:
    """Get all snapshots for a file."""
    data = redis.get(_get_snapshot_key(file_uuid))
    if data:
        return json.loads(data)
    return []


def switch_to_snapshot(file_uuid: str, snapshot_id: int, redis: Redis) -> Optional[str]:
    """Switch editor content to a specific snapshot version."""
    snapshots = get_snapshots(file_uuid, redis)
    for s in snapshots:
        if s["id"] == snapshot_id:
            content = s["content"]
            redis.set(_get_content_key(file_uuid), content)
            return content
    return None


def auto_save_to_disk(file_uuid: str, redis: Redis):
    """Save latest content from Redis to disk (called every 30 seconds)."""
    content = redis.get(_get_content_key(file_uuid))
    if not content:
        return

    file_path = _get_file_path(file_uuid)
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass