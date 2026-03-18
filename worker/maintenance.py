from sqlalchemy import delete, select
from shared.database import AsyncSessionLocal
from shared.models import ItemORM
from datetime import datetime, timedelta

async def cleanup_expired_items():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(ItemORM.id, ItemORM.created_at, ItemORM.retention_days).where(
                    ItemORM.retention_days > 0,
                    ItemORM.is_pinned == False
                )
            )
            rows = result.all()
            expired_ids = [
                row.id
                for row in rows
                if row.created_at < datetime.now() - timedelta(hours=row.retention_days)
            ]

            if not expired_ids:
                print("🧹 自动清理完成，未发现过期数据。")
                return

            delete_result = await session.execute(
                delete(ItemORM).where(ItemORM.id.in_(expired_ids))
            )
            print(f"🧹 自动清理完成，移除了 {delete_result.rowcount} 条过期数据。")
