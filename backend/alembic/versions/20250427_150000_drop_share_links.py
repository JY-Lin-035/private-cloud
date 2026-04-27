"""drop share_links table

Revision ID: 003
Revises: 002
Create Date: 2026-04-27 15:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '003'
down_revision = '002'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_table('share_links')


def downgrade():
    op.create_table(
        'share_links',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('path', sa.String(length=255), nullable=False),
        sa.Column('file_name', sa.String(length=255), nullable=True),
        sa.Column('link', sa.String(length=255), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
        sa.ForeignKeyConstraint(['owner_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('link')
    )
    op.create_index(op.f('ix_share_links_link'), 'share_links', ['link'], unique=True)
    op.create_index(op.f('ix_share_links_owner_id'), 'share_links', ['owner_id'], unique=False)
