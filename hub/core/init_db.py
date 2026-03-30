import asyncio
from shared.database import engine
from shared.models import Base, PluginRegistryORM
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert
from shared.logger import hub_log


async def ensure_runtime_tables():
    """在应用启动时补齐缺失的数据表，不破坏现有业务数据。"""
    async with engine.begin() as conn:
        hub_log.info("🧪 正在检查并开启 pgvector 扩展...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        hub_log.info("🧱 正在补齐缺失的数据表...")
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
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ALTER COLUMN is_starred SET DEFAULT FALSE"))
        await conn.execute(text("UPDATE user_item_states SET is_starred = FALSE WHERE is_starred IS NULL"))
        await conn.execute(text("""
            UPDATE user_item_states
            SET is_watch_later = TRUE
            WHERE COALESCE(is_starred, FALSE) = TRUE
              AND COALESCE(is_watch_later, FALSE) = FALSE
        """))
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ALTER COLUMN is_watch_later SET DEFAULT FALSE"))
        await conn.execute(text("ALTER TABLE IF EXISTS user_item_states ALTER COLUMN is_favorited SET DEFAULT FALSE"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_annotations_user_id ON user_annotations (user_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_annotations_item_id ON user_annotations (item_id)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_user_annotations_created_at ON user_annotations (created_at DESC)"))
        
        # 确保内置插件始终存在于注册表中 (即使不运行 init_db 也能在第一次启动时载入)
        hub_log.info("🌱 正在检查并补齐内置插件...")
        await conn.execute(text("""
            INSERT INTO plugins (plugin_id, name, module_path, is_enabled, version, installed_at)
            VALUES ('github_stars', 'GitHub Stars', 'worker.plugins.github.plugin', true, '1.0.0', CURRENT_TIMESTAMP)
            ON CONFLICT (plugin_id) DO NOTHING;
        """))


async def init_db():
    async with engine.begin() as conn:
        hub_log.info("🧪 正在检查并开启 pgvector 扩展...")
        # 必须先执行这个，否则 Vector(1536) 字段会报错
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        hub_log.info("🗑️ 正在清空旧数据表...")
        await conn.run_sync(Base.metadata.drop_all)
        
        hub_log.info("🏗️ 正在创建所有数据库表...")
        # 自动扫描所有继承自 Base 的模型（即我们的 ItemORM）
        await conn.run_sync(Base.metadata.create_all)
        
        hub_log.info("🌱 正在植入生命之种 (初始化插件)...")
        # 插入 GitHub 插件作为第一颗种子
        stmt = insert(PluginRegistryORM).values(
            plugin_id="github_stars",
            name="GitHub Stars",
            module_path="worker.plugins.github.plugin",
            is_enabled=True,
            version="1.0.0"
        )
        await conn.execute(stmt)
        
    hub_log.info("✅ 数据库初始化完成！Iris 的记忆神殿已建成。")

if __name__ == "__main__":
    asyncio.run(init_db())
