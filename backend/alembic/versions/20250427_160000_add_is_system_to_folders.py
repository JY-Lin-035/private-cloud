"""add is_system column to folders

Revision ID: 004
Revises: 003
Create Date: 2026-04-27 16:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('folders', sa.Column('is_system', sa.Boolean(), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('folders', 'is_system')
