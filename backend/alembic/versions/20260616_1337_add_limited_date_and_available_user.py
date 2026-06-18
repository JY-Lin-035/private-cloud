"""add limited_date and available_user columns to files and folders

Revision ID: 005
Revises: 004
Create Date: 2026-06-16 13:37:00

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '005'
down_revision = '004'
branch_labels = None
depends_on = None


def upgrade():
    # Add columns to folders table
    op.add_column('folders', sa.Column('limited_date', sa.TIMESTAMP(), nullable=True))
    op.add_column('folders', sa.Column('available_user', sa.Text(), nullable=True))

    # Add columns to files table
    op.add_column('files', sa.Column('limited_date', sa.TIMESTAMP(), nullable=True))
    op.add_column('files', sa.Column('available_user', sa.Text(), nullable=True))


def downgrade():
    # Remove columns from files table
    op.drop_column('files', 'available_user')
    op.drop_column('files', 'limited_date')

    # Remove columns from folders table
    op.drop_column('folders', 'available_user')
    op.drop_column('folders', 'limited_date')