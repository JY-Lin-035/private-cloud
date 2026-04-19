"""Initial migration

Revision ID: 001
Revises: 
Create Date: 2025-04-19 14:30:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create accounts table
    op.create_table(
        'accounts',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('password', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('signal_file_size', sa.BigInteger(), nullable=True),
        sa.Column('total_file_size', sa.BigInteger(), nullable=True),
        sa.Column('used_size', sa.BigInteger(), nullable=True),
        sa.Column('identity', sa.SmallInteger(), nullable=True),
        sa.Column('enable', sa.Boolean(), nullable=True),
        sa.Column('email_verified_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('delete_date', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_sign_in_date', sa.TIMESTAMP(), nullable=True),
        sa.Column('remember_token', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('email')
    )
    op.create_index(op.f('ix_accounts_email'), 'accounts', ['email'], unique=False)
    op.create_index(op.f('ix_accounts_name'), 'accounts', ['name'], unique=False)
    
    # Create share_links table
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
    op.create_index(op.f('ix_share_links_link'), 'share_links', ['link'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_share_links_link'), table_name='share_links')
    op.drop_table('share_links')
    op.drop_index(op.f('ix_accounts_name'), table_name='accounts')
    op.drop_index(op.f('ix_accounts_email'), table_name='accounts')
    op.drop_table('accounts')
