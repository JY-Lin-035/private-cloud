"""remove enable_preview_office flag (office preview moved fully client-side)

Revision ID: 017
Revises: 016
"""
from typing import Sequence, Union
from datetime import datetime

import sqlalchemy as sa
from alembic import op

revision: str = '017'
down_revision: Union[str, None] = '016'
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
    op.execute(_FLAGS.delete().where(_FLAGS.c.key == "enable_preview_office"))


def downgrade() -> None:
    now = datetime.utcnow()
    op.bulk_insert(_FLAGS, [
        {"key": "enable_preview_office", "enabled": False, "created_at": now, "updated_at": now,
         "description": "Office 伺服器端轉換預覽（LibreOffice）"},
    ])
