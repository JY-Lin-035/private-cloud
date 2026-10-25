"""add announcements table

Revision ID: 012
Revises: 011
Create Date: 2026-10-25 17:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'announcements' not in inspector.get_table_names():
        op.create_table(
            'announcements',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('content', sa.String(length=500), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False),
            sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
            sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade() -> None:
    op.drop_table('announcements')
