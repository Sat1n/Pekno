import asyncio

from sqlalchemy import text

from shared.database import engine
from shared.logger import hub_log
from shared.plugins.manager import plugin_manager


async def ensure_runtime_environment():
    """Ensure runtime-only database prerequisites after schema migrations."""
    async with engine.begin() as conn:
        hub_log.info("Checking and enabling the pgvector extension...")
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        hub_log.info("Ensuring built-in plugins exist in the registry...")
        await plugin_manager.ensure_builtin_plugins(conn)


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
