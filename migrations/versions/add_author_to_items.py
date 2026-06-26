"""add_author_to_items

Revision ID: a1b2c3d4e5f6
Revises: e3eb4bc180ca
Create Date: 2026-06-26 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'e3eb4bc180ca'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('items', sa.Column('author', sa.String(), nullable=True))
    op.create_index('ix_items_author', 'items', ['author'])
    # 从 metadata_extra 中提取作者信息
    op.execute("""
        UPDATE items
        SET author = COALESCE(
            metadata_extra->>'up_name',
            metadata_extra->>'author'
        )
        WHERE author IS NULL
    """)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_items_author', table_name='items')
    op.drop_column('items', 'author')
