import asyncio
from shared.database import AsyncSessionLocal
from sqlalchemy import select
from shared.models import ConfigORM
from shared.crypto import decrypt_value

async def main():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ConfigORM))
        configs = result.scalars().all()
        for config in configs:
            if config.key == "show_on_home":
                print(f"plugin_id: {config.plugin_id}, key: {config.key}, user_id: {config.user_id}, decrypted_value: {decrypt_value(config.value)}")
        if not any(c.key == "show_on_home" for c in configs):
            print("No show_on_home configs found in DB.")

asyncio.run(main())
