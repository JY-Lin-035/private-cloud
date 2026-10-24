"""add share_password to files and folders

Revision ID: 011
Revises: 010
Create Date: 2026-10-24 20:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column['name'] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    for table in ('files', 'folders'):
        if 'share_password' not in _column_names(table):
            op.add_column(table, sa.Column('share_password', sa.String(length=255), nullable=True))


def downgrade() -> None:
    for table in ('files', 'folders'):
        if 'share_password' in _column_names(table):
            op.drop_column(table, 'share_password')
