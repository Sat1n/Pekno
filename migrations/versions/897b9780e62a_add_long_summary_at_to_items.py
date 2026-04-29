"""add long_summary_at to items

Revision ID: 897b9780e62a
Revises: 6be3e5703b2d
Create Date: 2026-04-29 14:49:33.932974

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '897b9780e62a'
down_revision: Union[str, Sequence[str], None] = '6be3e5703b2d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('items', sa.Column('long_summary_at', sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column('items', 'long_summary_at')
