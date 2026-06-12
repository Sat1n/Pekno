import asyncio
from shared.database import AsyncSessionLocal
from sqlalchemy import select, and_
from shared.models import ConfigORM, ItemORM, UserItemStateORM
from shared.crypto import decrypt_value

async def main():
    user_id = "37e7f1b3-91f5-4787-b5f2-e030da902db5"
    async with AsyncSessionLocal() as session:
        # Get hidden plugins
        config_result = await session.execute(
            select(ConfigORM).where(
                ConfigORM.key == "show_on_home",
                ConfigORM.user_id == user_id
            )
        )
        hidden_plugins = []
        for config in config_result.scalars().all():
            if config.value:
                decrypted = decrypt_value(config.value)
                if decrypted and decrypted.lower() == "false":
                    hidden_plugins.append(config.plugin_id)
        
        print("Hidden plugins:", hidden_plugins)
        
        # Test the query
        stmt = (
            select(ItemORM, UserItemStateORM)
            .join(
                UserItemStateORM,
                and_(
                    UserItemStateORM.item_id == ItemORM.id,
                    UserItemStateORM.user_id == user_id,
                ),
            )
            .order_by(ItemORM.created_at.desc())
        )
        
        # Simulating home feed
        if hidden_plugins:
            stmt = stmt.where(ItemORM.source_type.notin_(hidden_plugins))
            
        result = await session.execute(stmt)
        rows = result.all()
        print(f"Total items returned: {len(rows)}")
        
        source_types = set(item.source_type for item, state in rows)
        print(f"Source types in results: {source_types}")
        
        # Query without hiding plugins to compare
        stmt_all = (
            select(ItemORM, UserItemStateORM)
            .join(
                UserItemStateORM,
                and_(
                    UserItemStateORM.item_id == ItemORM.id,
                    UserItemStateORM.user_id == user_id,
                ),
            )
            .order_by(ItemORM.created_at.desc())
        )
        result_all = await session.execute(stmt_all)
        rows_all = result_all.all()
        print(f"Total items without filter: {len(rows_all)}")
        source_types_all = set(item.source_type for item, state in rows_all)
        print(f"Source types without filter: {source_types_all}")

asyncio.run(main())
