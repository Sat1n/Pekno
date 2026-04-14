from __future__ import annotations

import time
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from shared.database import SYNC_DATABASE_URL
from shared.logger import hub_log

DEFAULT_DB_READY_RETRIES = 30
DEFAULT_DB_READY_DELAY_SECONDS = 2.0
CORE_TABLES = ("items", "plugins", "users")


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_alembic_config() -> Config:
    project_root = get_project_root()
    config = Config(str(project_root / "alembic.ini"))
    config.set_main_option("script_location", str(project_root / "migrations"))
    config.set_main_option("sqlalchemy.url", SYNC_DATABASE_URL)
    return config


def wait_for_database(
    *,
    max_attempts: int = DEFAULT_DB_READY_RETRIES,
    delay_seconds: float = DEFAULT_DB_READY_DELAY_SECONDS,
) -> None:
    hub_log.info(
        "Waiting for database readiness (max_attempts=%s, delay_seconds=%s)...",
        max_attempts,
        delay_seconds,
    )
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            engine = create_engine(SYNC_DATABASE_URL, future=True)
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                hub_log.info("Database is ready.")
                return
            finally:
                engine.dispose()
        except Exception as exc:  # pragma: no cover - exercised in runtime environments
            last_error = exc
            hub_log.warning(
                "Database is not ready yet (attempt %s/%s): %s",
                attempt,
                max_attempts,
                exc,
            )
            if attempt < max_attempts:
                time.sleep(delay_seconds)

    raise RuntimeError(
        f"Database did not become ready within timeout after {max_attempts} attempts."
    ) from last_error


def table_exists(table_name: str) -> bool:
    engine = create_engine(SYNC_DATABASE_URL, future=True)
    try:
        inspector = inspect(engine)
        return inspector.has_table(table_name)
    finally:
        engine.dispose()


def has_existing_schema() -> bool:
    return any(table_exists(table_name) for table_name in CORE_TABLES)


def alembic_version_exists() -> bool:
    return table_exists("alembic_version")


def stamp_head() -> None:
    hub_log.info("Stamping existing schema to the current Alembic head revision.")
    command.stamp(get_alembic_config(), "head")


def upgrade_head() -> None:
    hub_log.info("Applying pending Alembic migrations.")
    command.upgrade(get_alembic_config(), "head")


def run_migrations(
    *,
    max_attempts: int = DEFAULT_DB_READY_RETRIES,
    delay_seconds: float = DEFAULT_DB_READY_DELAY_SECONDS,
) -> None:
    wait_for_database(max_attempts=max_attempts, delay_seconds=delay_seconds)

    existing_schema = has_existing_schema()
    has_version_table = alembic_version_exists()

    if existing_schema and not has_version_table:
        hub_log.warning(
            "Detected an existing schema without alembic_version; stamping the database before upgrade."
        )
        stamp_head()

    upgrade_head()
