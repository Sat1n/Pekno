import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

DB_USER = os.getenv("POSTGRES_USER", "pekno")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "pekno_password")
DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "pekno")

def build_database_url(*, sync: bool = False, database_name: str | None = None) -> str:
    driver = "postgresql+psycopg" if sync else "postgresql+asyncpg"
    db_name = database_name or DB_NAME
    return f"{driver}://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{db_name}"


DATABASE_URL = build_database_url()
SYNC_DATABASE_URL = build_database_url(sync=True)

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_recycle=1800,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
