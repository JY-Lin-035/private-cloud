"""Quota-aware persistence for collaborative editor content.

Both the WebSocket `save`/`persist_text` messages and the 30s autosave
scheduler go through here, so collaborative writes can never bypass
per-file / total-quota limits or the accounting kept in `accounts.used_size`.
"""
import os
import uuid as uuid_lib
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models.account import Account
from app.models.file import File
from app.services.folder_service import FolderService


def content_size_ok(content: str | None) -> bool:
    if content is None:
        return False
    try:
        return len(content.encode("utf-8")) <= settings.MAX_COLLAB_CONTENT_BYTES
    except Exception:
        return False


def _storage_path(file: File) -> str:
    base = settings.STORAGE_BASE_PATH
    if not os.path.isabs(base):
        base = os.path.join(os.getcwd(), base)
    return os.path.join(base, file.uuid)


def persist_content(file_uuid: str, content: str) -> bool:
    """Atomically write editor content to disk with size + quota enforcement.

    Returns True on success or when there is nothing to change; False when the
    file is gone, over the per-file cap, or would exceed the account quota.
    """
    if not content_size_ok(content):
        return False
    data = content.encode("utf-8")
    db: Session = SessionLocal()
    try:
        # Cheap pre-read just to find the owning account.
        f = db.execute(select(File).where(File.uuid == file_uuid)).scalar_one_or_none()
        if f is None or f.deleted_at is not None:
            return False
        # Serialize ALL quota accounting on the account row first, then
        # re-read the File row under that lock (same account->file lock order
        # as upload finalize, so the two paths cannot deadlock each other).
        # Reading f.size before the lock let concurrent autosave + WS saves
        # compute deltas from stale sizes and drift used_size permanently.
        acct = db.query(Account).filter(Account.id == f.owner_id).with_for_update().first()
        if acct is None:
            return False
        db.refresh(f)
        if f is None or f.deleted_at is not None:
            return False

        path = _storage_path(f)
        # Skip no-op writes (avoids touching updated_at on every autosave).
        try:
            with open(path, "rb") as fh:
                if fh.read() == data:
                    return True
        except OSError:
            pass

        delta = len(data) - (f.size or 0)
        if delta > 0:
            if len(data) > (acct.signal_file_size or 0):
                return False
            if (acct.used_size or 0) + delta > (acct.total_file_size or 0):
                return False

        # Unique temp name: never share path+".tmp" between writers.
        tmp = f"{path}.{os.getpid()}.{uuid_lib.uuid4().hex}.tmp"
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(tmp, "wb") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        except OSError:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return False

        if delta:
            acct.used_size = max(0, (acct.used_size or 0) + delta)
        f.size = len(data)
        f.updated_at = datetime.utcnow()
        db.commit()
        if f.parent_folder_id and delta:
            FolderService(db)._update_parent_folder_size(f.parent_folder_id, delta)
        return True
    except Exception:
        db.rollback()
        return False
    finally:
        db.close()