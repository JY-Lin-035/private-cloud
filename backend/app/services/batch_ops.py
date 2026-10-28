"""Batch trash operations (soft delete / permanent delete / restore) executed as
ONE request with per-item deletion locks.

While an operation runs, every uuid in its scope (targets + full subtrees) is
marked with a short-TTL redis lock; routes that mutate or read a specific item
call assert_not_deleting() and answer 423 while the lock is held, so
concurrent tabs/devices cannot restore, move, download or re-share an item
that is mid-deletion.
"""
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
from sqlalchemy import select, update, delete as sa_delete

from app.config import settings
from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder

LOCK_TTL = 300
CHUNK = 500


def _k(uuid: str) -> str:
    return f"delLock:{uuid}"


def acquire(r, uuids: List[str]) -> Optional[List[str]]:
    """SETNX all lock keys; on conflict release what we took and return None."""
    got: List[str] = []
    for u in uuids:
        try:
            ok = r.set(_k(u), "1", nx=True, ex=LOCK_TTL)
        except Exception:
            release(r, got)  # redis down: keep operation usable, skip locking
            return got or []
        if not ok:
            release(r, got)
            return None
        got.append(u)
    return got


def release(r, uuids: List[str]) -> None:
    for u in uuids:
        try:
            r.delete(_k(u))
        except Exception:
            pass


def assert_not_deleting(r, *uuids) -> None:
    for u in uuids:
        if u and r.exists(_k(u)):
            raise HTTPException(status_code=423, detail="該項目正在刪除處理中，請稍後再試")


def _chunks(xs: List[str]):
    for i in range(0, len(xs), CHUNK):
        yield xs[i:i + CHUNK]


def _subtree_levels(db, user_id: int, top_uuids: List[str]) -> List[List[str]]:
    """BFS over folders. level0 = tops; deeper levels are children uuids."""
    levels: List[List[str]] = [top_uuids]
    frontier = top_uuids
    while frontier:
        nxt: List[str] = []
        for chunk in _chunks(frontier):
            nxt += list(db.execute(select(Folder.uuid).where(
                Folder.owner_id == user_id, Folder.parent_id.in_(chunk))).scalars().all())
        frontier = nxt
        if frontier:
            levels.append(frontier)
    return levels


def batch_operation(user_id: int, folders: List[str], files: List[str], mode: str, r) -> Dict[str, Any]:
    """mode: soft | permanent | restore. One transaction; blobs unlinked after commit."""
    if mode not in ("soft", "permanent", "restore"):
        raise HTTPException(status_code=400, detail="無效的操作模式")
    folders = list(dict.fromkeys([f for f in (folders or []) if f]))
    files = list(dict.fromkeys([f for f in (files or []) if f]))
    skipped: List[Dict[str, str]] = []
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        # ---------- validate top-level targets ----------
        top_folders: List[Folder] = []
        for chunk in _chunks(folders):
            top_folders += list(db.execute(select(Folder).where(
                Folder.owner_id == user_id, Folder.uuid.in_(chunk))).scalars().all())
        found = {f.uuid for f in top_folders}
        for u in folders:
            if u not in found:
                skipped.append({"uuid": u, "reason": "不存在或無權限"})
        kept = []
        for f in top_folders:
            if mode != "restore" and f.is_system:
                skipped.append({"uuid": f.uuid, "reason": "系統資料夾無法刪除"})
            elif mode == "restore" and not f.deleted_at:
                skipped.append({"uuid": f.uuid, "reason": "不在垃圾桶中"})
            elif mode == "soft" and f.deleted_at:
                skipped.append({"uuid": f.uuid, "reason": "已在垃圾桶中"})
            else:
                kept.append(f)
        top_folders = kept

        top_files: List[File] = []
        for chunk in _chunks(files):
            top_files += list(db.execute(select(File).where(
                File.owner_id == user_id, File.uuid.in_(chunk))).scalars().all())
        found = {f.uuid for f in top_files}
        for u in files:
            if u not in found:
                skipped.append({"uuid": u, "reason": "不存在或無權限"})
        kept = []
        for f in top_files:
            if mode == "restore" and not f.deleted_at:
                skipped.append({"uuid": f.uuid, "reason": "不在垃圾桶中"})
            elif mode == "soft" and f.deleted_at:
                skipped.append({"uuid": f.uuid, "reason": "已在垃圾桶中"})
            else:
                kept.append(f)
        top_files = kept

        folder_tops = [f.uuid for f in top_folders]
        file_tops = [f.uuid for f in top_files]
        if not folder_tops and not file_tops:
            return {"folders": 0, "files": 0, "freed_bytes": 0, "skipped": skipped}

        # ---------- subtrees ----------
        levels = _subtree_levels(db, user_id, folder_tops) if folder_tops else []
        subtree_uuids = [u for lv in levels for u in lv]
        descendants: List[File] = []
        for chunk in _chunks(subtree_uuids) if subtree_uuids else []:
            descendants += list(db.execute(select(File).where(
                File.owner_id == user_id, File.parent_folder_id.in_(chunk))).scalars().all())
        tfset = set(file_tops)
        descendants = [f for f in descendants if f.uuid not in tfset]

        scope = list(dict.fromkeys(subtree_uuids + file_tops + [f.uuid for f in descendants]))
        locks = acquire(r, scope)
        if locks is None:
            raise HTTPException(status_code=423, detail="部分項目正在刪除處理中，請稍後再試")
        try:
            n_folders = n_files = 0
            freed = 0
            now = datetime.utcnow()

            if mode == "soft":
                fuuids = file_tops + [f.uuid for f in descendants if not f.deleted_at]
                for chunk in _chunks(fuuids):
                    res = db.execute(update(File).where(
                        File.owner_id == user_id, File.uuid.in_(chunk), File.deleted_at.is_(None)
                    ).values(deleted_at=now, shared=None))
                    n_files += res.rowcount or 0
                for chunk in _chunks(subtree_uuids):
                    res = db.execute(update(Folder).where(
                        Folder.owner_id == user_id, Folder.uuid.in_(chunk), Folder.deleted_at.is_(None)
                    ).values(deleted_at=now))
                    n_folders += res.rowcount or 0
                db.commit()

            elif mode == "permanent":
                doomed_files = top_files + descendants
                seen: set = set()
                freed = 0
                for f in doomed_files:
                    if f.uuid not in seen:
                        seen.add(f.uuid)
                        freed += f.size or 0
                doomed_folders = set(subtree_uuids)
                by_parent: Dict[str, int] = {}
                for f in doomed_files:
                    if f.parent_folder_id and f.parent_folder_id not in doomed_folders:
                        by_parent[f.parent_folder_id] = by_parent.get(f.parent_folder_id, 0) + (f.size or 0)
                for tf in top_folders:
                    if tf.parent_id and tf.parent_id not in doomed_folders:
                        by_parent[tf.parent_id] = by_parent.get(tf.parent_id, 0) + (tf.size or 0)
                for chunk in _chunks(list(seen)):
                    res = db.execute(sa_delete(File).where(
                        File.owner_id == user_id, File.uuid.in_(chunk)))
                    n_files += res.rowcount or 0
                for lv in reversed(levels):
                    for chunk in _chunks(lv):
                        res = db.execute(sa_delete(Folder).where(
                            Folder.owner_id == user_id, Folder.uuid.in_(chunk)))
                        n_folders += res.rowcount or 0
                acct = db.query(Account).filter(Account.id == user_id).first()
                if acct and freed:
                    acct.used_size = max(0, (acct.used_size or 0) - freed)
                db.commit()
                from app.services.folder_service import FolderService
                fs = FolderService(db)
                for parent_uuid, delta in by_parent.items():
                    if delta:
                        fs._update_parent_folder_size(parent_uuid, -delta)
                base = settings.STORAGE_BASE_PATH
                for uuid in seen:
                    try:
                        p = os.path.join(base, uuid)
                        if os.path.isfile(p):
                            os.remove(p)
                    except OSError:
                        pass

            else:  # restore
                restore_folders = subtree_uuids
                restore_files = [f for f in top_files if f.deleted_at] + \
                                [f for f in descendants if f.deleted_at]
                live_names: Dict[str, set] = {}
                pids = sorted({(f.parent_folder_id or "") for f in restore_files} |
                              {tf.parent_id or "" for tf in top_folders})
                for pid in pids:
                    if not pid:
                        names = set(db.execute(select(File.name).where(
                            File.parent_folder_id.is_(None), File.deleted_at.is_(None))).scalars().all())
                        names |= set(db.execute(select(Folder.name).where(
                            Folder.parent_id.is_(None), Folder.deleted_at.is_(None),
                            Folder.owner_id == user_id)).scalars().all())
                        live_names[""] = names
                        continue
                    names = set(db.execute(select(File.name).where(
                        File.parent_folder_id == pid, File.deleted_at.is_(None))).scalars().all())
                    names |= set(db.execute(select(Folder.name).where(
                        Folder.parent_id == pid, Folder.deleted_at.is_(None),
                        Folder.owner_id == user_id)).scalars().all())
                    live_names[pid] = names
                from app.utils.pathing import unique_name
                for f in restore_files:
                    pid = f.parent_folder_id or ""
                    taken = live_names.setdefault(pid, set())
                    if f.name in taken:
                        f.name = unique_name(f.name, taken)
                        taken.add(f.name)
                    f.deleted_at = None
                db.flush()
                for chunk in _chunks(restore_folders):
                    db.execute(update(Folder).where(
                        Folder.owner_id == user_id, Folder.uuid.in_(chunk)).values(deleted_at=None))
                db.commit()
                n_folders, n_files = len(restore_folders), len(restore_files)

            return {"folders": n_folders, "files": n_files, "freed_bytes": freed, "skipped": skipped}
        finally:
            release(r, scope)
    finally:
        db.close()
