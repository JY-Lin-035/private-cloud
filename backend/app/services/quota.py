"""Single source of truth for storage quota/folder-size recalculation.

All three recalculation entry points (user self-service, admin per-user, and
the scheduled celery sweep) MUST use this logic. Historically each kept its own
copy of the query and they drifted: the on-demand ones were fixed to count
soft-deleted files while the scheduled one still excluded them, which
periodically re-opened the quota bypass (upload -> trash -> recalc -> quota
released while bytes still occupy disk). One implementation prevents that class
of regression.

Semantics (deliberate):
  - used_size   = sum of ALL File rows owned by the user (live + trashed),
                  because trashed bytes stay on disk until GC and the delete
                  path does not decrement used_size on soft delete.
  - folder.size = sum of ALL File rows whose parent is that folder (live +
                  trashed), matching the live soft-delete behavior which does
                  not decrement the parent folder size.
Does NOT commit; the caller owns the transaction.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.account import Account
from app.models.file import File
from app.models.folder import Folder


def recalc_user_storage(db: Session, user: Account) -> tuple[int, int]:
    """Recompute and assign folder.size and user.used_size.

    Returns (used_size, folder_count). Caller owns the transaction (commit).
    """
    folders = db.execute(
        select(Folder).where(Folder.owner_id == user.id)
    ).scalars().all()

    for folder in folders:
        sizes = db.execute(
            select(File.size).where(File.parent_folder_id == folder.uuid)
        ).scalars().all()
        folder.size = sum(int(s or 0) for s in sizes)

    # Safety: used_size must reflect every File row for the owner even if a
    # file references a parent folder that is missing/orphaned, so count
    # directly by owner as the source of truth.
    owner_sizes = db.execute(
        select(File.size).where(File.owner_id == user.id)
    ).scalars().all()
    total_by_owner = sum(int(s or 0) for s in owner_sizes)

    user.used_size = total_by_owner
    return total_by_owner, len(folders)
