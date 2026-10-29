"""files.updated_at to fractional-second precision (reliable edit-conflict detection)

Revision ID: 016
Revises: 015
"""
from typing import Sequence, Union
from alembic import op

revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE files MODIFY updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6)")


def downgrade() -> None:
    op.execute("ALTER TABLE files MODIFY updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
