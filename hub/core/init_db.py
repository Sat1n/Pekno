import asyncio
from shared.database import engine
from shared.models import Base, PluginRegistryORM
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from shared.logger import hub_log


async def ensure_runtime_tables():
    """Create any missing runtime tables without destroying existing data."""
    async with engine.begin() as conn:
        hub_log.info("🧪 Checking and enabling the pgvector extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        hub_log.info("🧱 Creating missing runtime tables and indexes...")
        await conn.run_sync(Base.metadata.create_all)
        # MVP 阶段先用轻量 schema bootstrap，后续可迁移到 Alembic。
        await conn.execute(text("ALTER TABLE IF EXISTS configs ADD COLUMN IF NOT EXISTS user_id VARCHAR DEFAULT 'system'"))
        await conn.execute(text("ALTER TABLE IF EXISTS configs ADD COLUMN IF NOT EXISTS id VARCHAR"))
        await conn.execute(text("UPDATE configs SET user_id = 'system' WHERE user_id IS NULL"))
        await conn.execute(text("UPDATE configs SET id = md5(plugin_id || ':' || key || ':' || user_id) WHERE id IS NULL"))
        await conn.execute(text("ALTER TABLE IF EXISTS configs ALTER COLUMN user_id SET DEFAULT 'system'"))
        await conn.execute(text("ALTER TABLE IF EXISTS configs ALTER COLUMN id SET NOT NULL"))
        await conn.execute(text("""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'configs_pkey'
          AND conrelid = 'configs'::regclass
    ) THEN
        ALTER TABLE configs DROP CONSTRAINT configs_pkey;
    END IF;
END $$;
"""))
        await conn.execute(text("""
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'configs_pkey'
          AND conrelid = 'configs'::regclass
    ) THEN
        ALTER TABLE configs ADD CONSTRAINT configs_pkey PRIMARY KEY (id);
    END IF;
END $$;
"""))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_configs_plugin_user_key ON configs (plugin_id, user_id, key)"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_invitation_codes_code ON invitation_codes (code)"))
        await conn.execute(text("ALTER TABLE IF EXISTS invitation_codes ADD COLUMN IF NOT EXISTS used_by_user_id VARCHAR"))
        await conn.execute(text("ALTER TABLE IF EXISTS personal_access_tokens ADD COLUMN IF NOT EXISTS is_admin BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE IF EXISTS personal_access_tokens ADD COLUMN IF NOT EXISTS scopes VARCHAR[]"))
        await conn.execute(text("ALTER TABLE IF EXISTS personal_access_tokens ADD COLUMN IF NOT EXISTS last_used_at TIMESTAMP"))
        await conn.execute(text("""
            UPDATE personal_access_tokens pat
            SET is_admin = CASE
                WHEN u.role IN ('admin', 'super_admin') THEN TRUE
                ELSE FALSE
            END
            FROM users u
            WHERE pat.user_id = u.id
              AND pat.is_admin IS NULL
        """))
        await conn.execute(text("""
            UPDATE personal_access_tokens
            SET scopes = ARRAY['read:knowledge', 'write:star']
            WHERE scopes IS NULL
        """))
        await conn.execute(text("ALTER TABLE IF EXISTS personal_access_tokens ALTER COLUMN is_admin SET DEFAULT FALSE"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_personal_access_tokens_token ON personal_access_tokens (token)"))
        await conn.execute(text("ALTER TABLE IF EXISTS items ADD COLUMN IF NOT EXISTS file_hash VARCHAR"))
        await conn.execute(text("ALTER TABLE IF EXISTS items ADD COLUMN IF NOT EXISTS local_asset_path VARCHAR"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_items_file_hash ON items (file_hash)"))
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ADD COLUMN IF NOT EXISTS is_watch_later BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ADD COLUMN IF NOT EXISTS is_favorited BOOLEAN DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ADD COLUMN IF NOT EXISTS vault_category_id VARCHAR"))
        await conn.execute(text("""
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = 'user_item_states'
          AND column_name = 'is_starred'
    ) THEN
        ALTER TABLE user_item_states ALTER COLUMN is_starred SET DEFAULT FALSE;
        UPDATE user_item_states SET is_starred = FALSE WHERE is_starred IS NULL;
        UPDATE user_item_states
        SET is_watch_later = TRUE
        WHERE COALESCE(is_starred, FALSE) = TRUE
          AND COALESCE(is_watch_later, FALSE) = FALSE;
    END IF;
END $$;
"""))
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ALTER COLUMN is_watch_later SET DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ALTER COLUMN is_favorited SET DEFAULT FALSE"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_item_states_vault_category_id ON user_item_states (vault_category_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_vault_categories_user_id ON vault_categories (user_id)"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_vault_categories_user_name ON vault_categories (user_id, name)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_annotations_user_id ON user_annotations (user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_annotations_item_id ON user_annotations (item_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_annotations_created_at ON user_annotations (created_at DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_notifications_user_id ON user_notifications (user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_notifications_status ON user_notifications (status)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_notifications_created_at ON user_notifications (created_at DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_api_usage_created_at ON api_usage (created_at DESC)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_api_usage_model_name ON api_usage (model_name)"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_system_configs_key ON system_configs (key)"))
        
        # Ensure built-in plugins always exist in the registry, even on first boot.
        hub_log.info("🌱 Ensuring built-in plugins exist in the registry...")
        await conn.execute(text("""
            INSERT INTO plugins (plugin_id, name, module_path, is_enabled, version, installed_at)
            VALUES ('github_stars', 'GitHub Stars', 'worker.plugins.github.plugin', true, '1.0.0', CURRENT_TIMESTAMP)
            ON CONFLICT (plugin_id) DO NOTHING;
        """))


async def init_db():
    async with engine.begin() as conn:
        hub_log.info("🧪 Checking and enabling the pgvector extension...")
        # This must run before table creation, otherwise Vector(1536) fields will fail.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        hub_log.info("🗑️ Dropping existing database tables...")
        await conn.run_sync(Base.metadata.drop_all)

        hub_log.info("🏗️ Creating all database tables...")
        # Automatically discover all SQLAlchemy models inheriting from Base.
        await conn.run_sync(Base.metadata.create_all)

        hub_log.info("🌱 Seeding built-in plugins...")
        # Insert the GitHub plugin as the first seed.
        stmt = insert(PluginRegistryORM).values(
            plugin_id="github_stars",
            name="GitHub Stars",
            module_path="worker.plugins.github.plugin",
            is_enabled=True,
            version="1.0.0"
        )
        await conn.execute(stmt)
        
    hub_log.info("✅ Database initialization completed successfully.")

if __name__ == "__main__":
    asyncio.run(init_db())
