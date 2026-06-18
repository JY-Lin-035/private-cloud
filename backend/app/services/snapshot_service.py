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
SNAPSHOT_INTERVAL = settings.SNAPSHOT_INTERVAL
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


def _normalize_snapshots(snapshots: List[Dict]) -> List[Dict]:
    by_id = {}
    for snapshot in snapshots:
        snapshot_id = snapshot.get("id")
        if snapshot_id is not None:
            by_id[str(snapshot_id)] = snapshot

    def sort_key(snapshot: Dict) -> int:
        try:
            return int(snapshot.get("id", 0))
        except (TypeError, ValueError):
            return 0

    return sorted(
        by_id.values(),
        key=sort_key,
        reverse=True
    )[:MAX_SNAPSHOTS]


def save_snapshot(file_uuid: str, redis: Redis):
    """Save current content as a snapshot (called every 15 minutes)."""
    content = redis.get(_get_content_key(file_uuid))
    if not content or not content.strip():
        return

    snapshots = get_snapshots(file_uuid, redis)

    # Add new snapshot
    new_snapshot = {
        "id": time.time_ns(),
        "content": content,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }
    snapshots.append(new_snapshot)

    snapshots = _normalize_snapshots(snapshots)

    redis.set(_get_snapshot_key(file_uuid), json.dumps(snapshots))


def get_snapshots(file_uuid: str, redis: Redis) -> List[Dict]:
    """Get all snapshots for a file."""
    data = redis.get(_get_snapshot_key(file_uuid))
    if data:
        snapshots = _normalize_snapshots(json.loads(data))
        redis.set(_get_snapshot_key(file_uuid), json.dumps(snapshots))
        return snapshots
    return []


def switch_to_snapshot(file_uuid: str, snapshot_id: int | str, redis: Redis) -> Optional[str]:
    """Switch editor content to a specific snapshot version."""
    snapshots = get_snapshots(file_uuid, redis)
    for s in snapshots:
        if str(s["id"]) == str(snapshot_id):
            content = s["content"]
            redis.set(_get_content_key(file_uuid), content)
            return content
    return None


def auto_save_to_disk(file_uuid: str, redis: Redis):
    """Save latest content from Redis to disk (called every 30 seconds)."""
    content = redis.get(_get_content_key(file_uuid))
    if not content or not content.strip():
        return

    file_path = _get_file_path(file_uuid)
    if not file_path:
        return

    try:
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
    except Exception:
        pass
