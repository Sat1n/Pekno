import os
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

# 1. 构造数据库连接字符串
# 这里的格式是：postgresql+asyncpg://用户名:密码@地址:端口/数据库名
# 对应我们 docker-compose.yml 里的配置
DB_USER = os.getenv("POSTGRES_USER", "natis")
DB_PASS = os.getenv("POSTGRES_PASSWORD", "pekno_password")
DB_HOST = os.getenv("POSTGRES_HOST", "127.0.0.1")
DB_PORT = os.getenv("POSTGRES_PORT", "5432")
DB_NAME = os.getenv("POSTGRES_DB", "pekno_iris")

DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

# 2. 创建异步引擎 (Async Engine)
# echo=True 可以让你在控制台看到 SQLAlchemy 生成的原始 SQL 语句，开发阶段很有用
engine = create_async_engine(
    DATABASE_URL, 
    echo=False, 
    future=True
)

# 3. 创建异步会话工厂 (Async Session Factory)
# expire_on_commit=False 是异步操作中的标准做法，防止提交后对象属性失效
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False
)

# 4. 提供一个获取数据库连接的辅助函数 (用于 FastAPI 依赖注入或 Worker 内部调用)
async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()
