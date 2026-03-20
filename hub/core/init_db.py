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
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_configs_plugin_user_key ON configs (plugin_id, user_id, key)"))
        await conn.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_invitation_codes_code ON invitation_codes (code)"))
        await conn.execute(text("ALTER TABLE IF EXISTS invitation_codes ADD COLUMN IF NOT EXISTS used_by_user_id VARCHAR"))


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
