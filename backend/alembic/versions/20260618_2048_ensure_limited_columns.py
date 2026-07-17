"""ensure limited_date and available_user columns exist

Revision ID: 009
Revises: 008
Create Date: 2026-06-18 20:48:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '009'
down_revision: Union[str, None] = '008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column['name'] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    folder_columns = _column_names('folders')
    if 'limited_date' not in folder_columns:
        op.add_column('folders', sa.Column('limited_date', sa.TIMESTAMP(), nullable=True))
    if 'available_user' not in folder_columns:
        op.add_column('folders', sa.Column('available_user', sa.Text(), nullable=True))

    file_columns = _column_names('files')
    if 'limited_date' not in file_columns:
        op.add_column('files', sa.Column('limited_date', sa.TIMESTAMP(), nullable=True))
    if 'available_user' not in file_columns:
        op.add_column('files', sa.Column('available_user', sa.Text(), nullable=True))


def downgrade() -> None:
    file_columns = _column_names('files')
    if 'available_user' in file_columns:
        op.drop_column('files', 'available_user')
    if 'limited_date' in file_columns:
        op.drop_column('files', 'limited_date')

    folder_columns = _column_names('folders')
    if 'available_user' in folder_columns:
        op.drop_column('folders', 'available_user')
    if 'limited_date' in folder_columns:
        op.drop_column('folders', 'limited_date')
