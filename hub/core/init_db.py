import asyncio
from hub.core.database import engine
from hub.core.database_models import Base
from sqlalchemy import text
from hub.core.logger import hub_log

async def init_db():
    async with engine.begin() as conn:
        hub_log.info("🧪 正在检查并开启 pgvector 扩展...")
        # 必须先执行这个，否则 Vector(1536) 字段会报错
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        
        hub_log.info("🏗️ 正在创建所有数据库表...")
        # 自动扫描所有继承自 Base 的模型（即我们的 ItemORM）
        await conn.run_sync(Base.metadata.create_all)
        
    hub_log.info("✅ 数据库初始化完成！Iris 的记忆神殿已建成。")

if __name__ == "__main__":
    asyncio.run(init_db())