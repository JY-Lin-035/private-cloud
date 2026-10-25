"""add ip_control table

Revision ID: 013
Revises: 012
Create Date: 2026-10-25 19:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '013'
down_revision: Union[str, None] = '012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'ip_control' not in inspector.get_table_names():
        op.create_table(
            'ip_control',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('subject_type', sa.String(length=16), nullable=False),   # ip | ip_token | user
            sa.Column('ip', sa.String(length=45), nullable=True),
            sa.Column('token', sa.String(length=64), nullable=True),           # share token for ip_token
            sa.Column('user_id', sa.Integer(), nullable=True),
            sa.Column('username', sa.String(length=128), nullable=True),
            sa.Column('action', sa.String(length=8), nullable=False, server_default='slow'),   # slow | block
            sa.Column('scope', sa.String(length=16), nullable=False, server_default='transfer'),  # transfer | full
            sa.Column('direction', sa.String(length=8), nullable=False, server_default='both'),   # up | down | both
            sa.Column('delay_ms', sa.Integer(), nullable=False, server_default='2000'),
            sa.Column('upload_kbps', sa.Integer(), nullable=True),
            sa.Column('download_kbps', sa.Integer(), nullable=True),
            sa.Column('reason', sa.String(length=255), nullable=True),
            sa.Column('auto', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('created_by', sa.Integer(), nullable=True),
            sa.Column('expires_at', sa.TIMESTAMP(), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
            sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
        )
        op.create_index('ix_ip_control_ip', 'ip_control', ['ip'])
        op.create_index('ix_ip_control_user', 'ip_control', ['user_id'])


def downgrade() -> None:
    op.drop_table('ip_control')
