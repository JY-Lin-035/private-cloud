"""seed file-preview feature flags (default OFF)

Revision ID: 015
Revises: 014
Create Date: 2026-10-28 21:30:00
"""
from typing import Sequence, Union
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FLAGS = sa.table(
    "feature_flags",
    sa.column("key", sa.String),
    sa.column("enabled", sa.Boolean),
    sa.column("description", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("updated_at", sa.DateTime),
)


def upgrade() -> None:
    now = datetime.utcnow()
    op.bulk_insert(_FLAGS, [
        {"key": "enable_file_preview", "enabled": False, "created_at": now, "updated_at": now,
         "description": "檔案預覽／建立／編輯（文字系＋媒體＋Office）"},
        {"key": "enable_preview_office", "enabled": False, "created_at": now, "updated_at": now,
         "description": "Office 伺服器端轉換預覽（LibreOffice）"},
    ])


def downgrade() -> None:
    op.execute(_FLAGS.delete().where(_FLAGS.c.key.in_(
        ["enable_file_preview", "enable_preview_office"])))
