"""add_plugin_id_to_items

Revision ID: e3eb4bc180ca
Revises: 5bc497f79b64
Create Date: 2026-05-30 00:50:14.224715

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e3eb4bc180ca'
down_revision: Union[str, Sequence[str], None] = '5bc497f79b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('items', sa.Column('plugin_id', sa.String(), nullable=True))
    op.create_index('ix_items_plugin_id', 'items', ['plugin_id'])
    op.execute("UPDATE items SET plugin_id = source_type WHERE plugin_id IS NULL")


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_items_plugin_id', table_name='items')
    op.drop_column('items', 'plugin_id')
