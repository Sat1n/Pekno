"""rename_github_stars_plugin_id

Revision ID: 5bc497f79b64
Revises: cdb49f938e99
Create Date: 2026-05-30 00:04:04.654765

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5bc497f79b64'
down_revision: Union[str, Sequence[str], None] = 'cdb49f938e99'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("""
        INSERT INTO plugins (plugin_id, name, module_path, is_enabled, version, installed_at)
        SELECT 'github_star', name, module_path, is_enabled, version, installed_at
        FROM plugins WHERE plugin_id = 'github_stars'
        ON CONFLICT (plugin_id) DO NOTHING;
    """)
    op.execute("""
        DELETE FROM configs WHERE plugin_id = 'github_star' AND EXISTS (
            SELECT 1 FROM configs c2 
            WHERE c2.plugin_id = 'github_stars' 
            AND c2.user_id = configs.user_id 
            AND c2.key = configs.key
        );
    """)
    op.execute("UPDATE configs SET plugin_id = 'github_star' WHERE plugin_id = 'github_stars'")
    op.execute("DELETE FROM plugins WHERE plugin_id = 'github_stars'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("""
        INSERT INTO plugins (plugin_id, name, module_path, is_enabled, version, installed_at)
        SELECT 'github_stars', name, module_path, is_enabled, version, installed_at
        FROM plugins WHERE plugin_id = 'github_star'
        ON CONFLICT (plugin_id) DO NOTHING;
    """)
    op.execute("""
        DELETE FROM configs WHERE plugin_id = 'github_stars' AND EXISTS (
            SELECT 1 FROM configs c2 
            WHERE c2.plugin_id = 'github_star' 
            AND c2.user_id = configs.user_id 
            AND c2.key = configs.key
        );
    """)
    op.execute("UPDATE configs SET plugin_id = 'github_stars' WHERE plugin_id = 'github_star'")
    op.execute("DELETE FROM plugins WHERE plugin_id = 'github_star'")
