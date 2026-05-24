"""add_preferred_locale_to_users

Revision ID: cdb49f938e99
Revises: 897b9780e62a
Create Date: 2026-05-25 01:21:44.791401

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'cdb49f938e99'
down_revision: Union[str, Sequence[str], None] = '897b9780e62a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('preferred_locale', sa.String(), server_default='zh-CN', nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'preferred_locale')
