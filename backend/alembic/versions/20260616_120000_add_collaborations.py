"""add collaborations table

Revision ID: 005
Revises: 004
Create Date: 2026-06-16 16:00:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'collaborations',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('file_uuid', sa.String(36), nullable=False),
        sa.Column('owner_id', sa.Integer(), nullable=False),
        sa.Column('collaborator_id', sa.Integer(), nullable=False),
        sa.Column('permission', sa.String(20), nullable=False, server_default='editor'),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['file_uuid'], ['files.uuid'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['collaborator_id'], ['accounts.id'], ondelete='CASCADE'),
        sa.UniqueConstraint('file_uuid', 'collaborator_id', name='uq_collab_file_user'),
    )
    op.create_index(op.f('ix_collaborations_file_uuid'), 'collaborations', ['file_uuid'])
    op.create_index(op.f('ix_collaborations_owner_id'), 'collaborations', ['owner_id'])
    op.create_index(op.f('ix_collaborations_collaborator_id'), 'collaborations', ['collaborator_id'])


def downgrade():
    op.drop_index(op.f('ix_collaborations_collaborator_id'), table_name='collaborations')
    op.drop_index(op.f('ix_collaborations_owner_id'), table_name='collaborations')
    op.drop_index(op.f('ix_collaborations_file_uuid'), table_name='collaborations')
    op.drop_table('collaborations')