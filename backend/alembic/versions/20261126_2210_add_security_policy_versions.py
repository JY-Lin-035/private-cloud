"""add security_policy_versions table (round 24 PR③: versioned risk thresholds)

Revision ID: 018
Revises: 017
Create Date: 2026-11-26 22:10:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '018'
down_revision: Union[str, None] = '017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'security_policy_versions' not in inspector.get_table_names():
        op.create_table(
            'security_policy_versions',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('payload', sa.Text(), nullable=False),      # JSON {policy_id: int}
            sa.Column('diff', sa.Text(), nullable=True),          # JSON {policy_id: {before, after}}
            sa.Column('reason', sa.String(length=255), nullable=True),
            sa.Column('actor', sa.String(length=128), nullable=True),
            sa.Column('actor_id', sa.Integer(), nullable=True),
            sa.Column('parent_version', sa.Integer(), nullable=True),
            sa.Column('action', sa.String(length=16), nullable=False, server_default='update'),
            sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
            sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )


def downgrade() -> None:
    op.drop_table('security_policy_versions')
