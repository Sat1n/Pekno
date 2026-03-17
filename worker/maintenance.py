from sqlalchemy import delete
from shared.database import AsyncSessionLocal
from shared.models import ItemORM
from datetime import datetime, timedelta

async def cleanup_expired_items():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # 找到那些：非永久、已过期、且没有被 Pin 住的数据
            stmt = delete(ItemORM).where(
                ItemORM.retention_days > 0,
                ItemORM.created_at < datetime.now() - timedelta(days=ItemORM.retention_days),
                ItemORM.is_pinned == False
            )
            result = await session.execute(stmt)
            print(f"🧹 自动清理完成，移除了 {result.rowcount} 条过期数据。")