"""Single source of truth for storage quota/folder-size recalculation.

All three recalculation entry points (user self-service, admin per-user, and
the scheduled celery sweep) MUST use this logic. Historically each kept its own
copy of the query and they drifted: the on-demand ones were fixed to count
soft-deleted files while the scheduled one still excluded them, which
periodically re-opened the quota bypass (upload -> trash -> recalc -> quota
released while bytes still occupy disk). One implementation prevents that class
of regression.

Semantics (deliberate, aligned with the incremental bookkeeping in
folder_service._update_parent_folder_size):
  - folder.size = RECURSIVE subtree total (direct files incl. trashed + every
    descendant folder's files), because uploads add every byte to ALL ancestors
    and permanent folder-delete subtracts folder.size from used_size on that
    basis. A direct-children-only recalc would desubtract on delete.
  - used_size   = sum of ALL File rows owned by the user (live + trashed + any
    orphaned parent refs), i.e. bytes actually on disk until GC.
Does NOT commit; the caller owns the transaction.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder


def recalc_user_storage(db: Session, user: Account) -> tuple[int, int]:
    """Recompute and assign folder.size (recursive) and user.used_size.

    Returns (used_size, folder_count). Caller owns the transaction (commit).
    """
    folders = db.execute(
        select(Folder).where(Folder.owner_id == user.id)
    ).scalars().all()

    # Direct file bytes per parent-folder uuid (trash included on purpose).
    rows = db.execute(
        select(File.parent_folder_id, func.coalesce(func.sum(File.size), 0))
        .where(File.owner_id == user.id)
        .group_by(File.parent_folder_id)
    ).all()
    direct = {(pf or ""): int(s or 0) for pf, s in rows}

    # parent_id holds the parent folder's UUID string.
    by_parent: dict[str, list[Folder]] = {}
    for f in folders:
        by_parent.setdefault(f.parent_id or "", []).append(f)

    memo: dict[int, int] = {}

    def subtree(folder: Folder) -> int:
        if folder.id in memo:
            return memo[folder.id]
        memo[folder.id] = -1  # cycle guard
        total = direct.get(folder.uuid, 0)
        for child in by_parent.get(folder.uuid, []):
            c = subtree(child)
            if c > 0:
                total += c
        memo[folder.id] = total
        return total

    for f in folders:
        f.size = subtree(f)

    # used_size = every byte of every File row of the owner (incl. orphans).
    owner_total = db.execute(
        select(func.coalesce(func.sum(File.size), 0)).where(File.owner_id == user.id)
    ).scalar_one()
    total_by_owner = int(owner_total or 0)

    user.used_size = total_by_owner
    return total_by_owner, len(folders)
