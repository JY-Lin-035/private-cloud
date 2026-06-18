"""merge init and limited_date heads

Revision ID: 472c0a2b493f
Revises: 30d0b9a02f68, 005
Create Date: 2026-06-18 15:05:21.059374

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '472c0a2b493f'
down_revision: Union[str, None] = ('30d0b9a02f68', '005')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
