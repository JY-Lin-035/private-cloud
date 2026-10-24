"""Build streamed zip archives for folder / bulk downloads (no temp files)."""
import os
from urllib.parse import quote

from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.file import File
from app.models.folder import Folder
from app.utils.pathing import unique_name
from zipstream import ZipStream


def collect_zip_items(db: Session, user_id: int, file_uuids: list[str], folder_uuids: list[str]):
    """Resolve selected files/folders into (fs_path, arcname) pairs.

    Selections covered by an ancestor selection are dropped (no duplicates in
    the zip); top-level arcname collisions are auto-renamed.
    """
    folder_uuids = list(dict.fromkeys(folder_uuids))
    file_uuids = list(dict.fromkeys(file_uuids))

    folders = db.execute(
        select(Folder).where(Folder.uuid.in_(folder_uuids), Folder.owner_id == user_id, Folder.deleted_at.is_(None))
    ).scalars().all()
    files = db.execute(
        select(File).where(File.uuid.in_(file_uuids), File.owner_id == user_id, File.deleted_at.is_(None))
    ).scalars().all()

    all_folders = db.execute(select(Folder).where(Folder.owner_id == user_id)).scalars().all()

    folder_by_uuid = {f.uuid: f for f in all_folders}
    selected_folder_uuids = {f.uuid for f in folders}

    def has_selected_folder_ancestor(parent_uuid):
        cur = folder_by_uuid.get(parent_uuid)
        guard = 0
        while cur and guard < 64:
            if cur.uuid in selected_folder_uuids:
                return True
            cur = folder_by_uuid.get(cur.parent_id)
            guard += 1
        return False

    def is_covered(folder):
        cur = folder_by_uuid.get(folder.parent_id)
        guard = 0
        while cur and guard < 64:
            if cur.uuid in selected_folder_uuids and cur.uuid != folder.uuid:
                return True
            cur = folder_by_uuid.get(cur.parent_id)
            guard += 1
        return False

    kept_folders = [f for f in folders if not is_covered(f)]
    kept_files = [f for f in files if not has_selected_folder_ancestor(f.parent_folder_id)]

    items: list[tuple[str, str]] = []
    root_names: set[str] = set()

    for f in kept_files:
        arc = unique_name(f.name, root_names)
        root_names.add(arc)
        items.append((f.storage_path, arc))

    for d in kept_folders:
        root = unique_name(d.name, root_names)
        root_names.add(root)
        queue = [(d.uuid, root + '/')]
        while queue:
            cur_uuid, prefix = queue.pop()
            children = db.execute(
                select(Folder).where(Folder.parent_id == cur_uuid, Folder.deleted_at.is_(None))
            ).scalars().all()
            for c in children:
                queue.append((c.uuid, prefix + c.name + '/'))
                # preserve empty directories
                child_files = db.execute(
                    select(File).where(File.parent_folder_id == c.uuid, File.deleted_at.is_(None))
                ).scalars().all()
                if not child_files:
                    items.append((None, prefix + c.name + '/'))
            child_files = db.execute(
                select(File).where(File.parent_folder_id == cur_uuid, File.deleted_at.is_(None))
            ).scalars().all()
            for file in child_files:
                items.append((file.storage_path, prefix + file.name))

    return items, len(kept_files), len(kept_folders)


def _prepare_zipstream(items) -> ZipStream:
    zs = ZipStream()
    for fs_path, arcname in items:
        if fs_path is None:
            zs.add(b'', arcname)  # directory entry
        elif os.path.isfile(fs_path):
            zs.add_path(fs_path, arcname)
    return zs


def zip_bytes_iter(items):
    """Synchronous chunk iterator (used directly in tests / streaming)."""
    yield from _prepare_zipstream(items)


def build_zip_response(items, display_name: str) -> StreamingResponse:
    zs = _prepare_zipstream(items)
    headers = {'Content-Disposition': f"attachment; filename*=UTF-8''{quote(display_name)}.zip"}
    try:
        headers['Content-Length'] = str(len(zs))
    except Exception:
        pass
    return StreamingResponse(zs, media_type='application/zip', headers=headers)
