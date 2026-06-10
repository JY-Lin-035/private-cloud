"""Add folders and files tables

Revision ID: 002
Revises: 001
Create Date: 2025-04-27 14:00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create folders table
    op.create_table(
        'folders',
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('parent_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=30), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False),
        sa.Column('shared', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_id'], ['folders.uuid'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.UniqueConstraint('shared', name='uq_folders_shared_non_null')
    )
    op.create_index(op.f('ix_folders_uuid'), 'folders', ['uuid'], unique=False)
    op.create_index(op.f('ix_folders_owner_id'), 'folders', ['owner_id'], unique=False)
    op.create_index(op.f('ix_folders_parent_id'), 'folders', ['parent_id'], unique=False)
    op.create_index(op.f('ix_folders_deleted_at'), 'folders', ['deleted_at'], unique=False)
    
    # Create files table
    op.create_table(
        'files',
        sa.Column('uuid', sa.String(length=36), nullable=False),
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('parent_folder_id', sa.String(length=36), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('size', sa.BigInteger(), nullable=False),
        sa.Column('mime_type', sa.String(length=100), nullable=True),
        sa.Column('storage_path', sa.String(length=512), nullable=False),
        sa.Column('shared', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=False),
        sa.Column('deleted_at', sa.TIMESTAMP(), nullable=True),
        sa.ForeignKeyConstraint(['owner_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['parent_folder_id'], ['folders.uuid'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('uuid'),
        sa.UniqueConstraint('shared', name='uq_files_shared_non_null')
    )
    op.create_index(op.f('ix_files_uuid'), 'files', ['uuid'], unique=False)
    op.create_index(op.f('ix_files_owner_id'), 'files', ['owner_id'], unique=False)
    op.create_index(op.f('ix_files_parent_folder_id'), 'files', ['parent_folder_id'], unique=False)
    op.create_index(op.f('ix_files_deleted_at'), 'files', ['deleted_at'], unique=False)
    
    # Remove remember_token from accounts table
    op.drop_column('accounts', 'remember_token')


def downgrade() -> None:
    # Add remember_token back to accounts table
    op.add_column('accounts', sa.Column('remember_token', sa.String(length=100), nullable=True))
    
    # Drop files table
    op.drop_index(op.f('ix_files_deleted_at'), table_name='files')
    op.drop_index(op.f('ix_files_parent_folder_id'), table_name='files')
    op.drop_index(op.f('ix_files_owner_id'), table_name='files')
    op.drop_index(op.f('ix_files_uuid'), table_name='files')
    op.drop_table('files')
    
    # Drop folders table
    op.drop_index(op.f('ix_folders_deleted_at'), table_name='folders')
    op.drop_index(op.f('ix_folders_parent_id'), table_name='folders')
    op.drop_index(op.f('ix_folders_owner_id'), table_name='folders')
    op.drop_index(op.f('ix_folders_uuid'), table_name='folders')
    op.drop_table('folders')
