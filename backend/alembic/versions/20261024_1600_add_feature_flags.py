"""add feature_flags table and seed defaults

Revision ID: 010
Revises: 009
Create Date: 2026-10-24 16:00:00

"""
from typing import Sequence, Union
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '010'
down_revision: Union[str, None] = '009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FEATURE_FLAGS = (
    ("allow_registration", 1, "是否開放新帳號註冊"),
    ("enable_verification_email", 1, "註冊/登入驗證信是否發送"),
    ("enable_auth_code_email", 1, "密碼重設/信箱變更驗證碼信是否發送"),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'feature_flags' not in inspector.get_table_names():
        op.create_table(
            'feature_flags',
            sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
            sa.Column('key', sa.String(length=64), nullable=False),
            sa.Column('enabled', sa.Boolean(), nullable=False),
            sa.Column('description', sa.String(length=255), nullable=True),
            sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
            sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
            sa.PrimaryKeyConstraint('id'),
            sa.UniqueConstraint('key'),
        )
        op.create_index('ix_feature_flags_key', 'feature_flags', ['key'])

    flags = sa.table(
        'feature_flags',
        sa.column('key', sa.String),
        sa.column('enabled', sa.Boolean),
        sa.column('description', sa.String),
        sa.column('created_at', sa.TIMESTAMP),
        sa.column('updated_at', sa.TIMESTAMP),
    )
    now = datetime.utcnow()
    existing = {
        row[0] for row in op.get_bind().execute(sa.text("SELECT `key` FROM feature_flags"))
    }
    op.bulk_insert(
        flags,
        [
            {"key": k, "enabled": bool(v), "description": d, "created_at": now, "updated_at": now}
            for k, v, d in FEATURE_FLAGS if k not in existing
        ],
    )


def downgrade() -> None:
    op.drop_index('ix_feature_flags_key', table_name='feature_flags')
    op.drop_table('feature_flags')
