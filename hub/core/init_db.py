import asyncio

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert

from shared.database import engine
from shared.logger import hub_log
from shared.models import PluginRegistryORM


async def ensure_runtime_environment():
    """Ensure runtime-only database prerequisites after schema migrations."""
    async with engine.begin() as conn:
        hub_log.info("Checking and enabling the pgvector extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        hub_log.info("Ensuring built-in plugins exist in the registry...")
        stmt = insert(PluginRegistryORM).values(
            plugin_id="github_stars",
            name="GitHub Stars",
            module_path="worker.plugins.github.plugin",
            is_enabled=True,
            version="1.0.0",
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["plugin_id"])
        await conn.execute(stmt)


async def ensure_runtime_tables():
    """Backward-compatible alias kept during migration bootstrap transition."""
    await ensure_runtime_environment()


async def init_db():
    hub_log.warning(
        "Direct schema bootstrap is deprecated. Please run Alembic migrations instead."
    )
    await ensure_runtime_environment()
    hub_log.info("Runtime environment initialization completed successfully.")


if __name__ == "__main__":
    asyncio.run(init_db())
