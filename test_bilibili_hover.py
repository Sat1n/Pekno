import asyncio
import sys
import json
sys.path.append(r'F:\Cardinal\Pekno')
from plugins_dev.bilibili_sync.plugin import plugin

async def main():
    item_url = "https://www.bilibili.com/video/BV1vA411b7ip"
    user_config = {}
    
    blocks = await plugin.get_hover_blocks(item_url, user_config)
    print(json.dumps(blocks, indent=2, ensure_ascii=False))

if __name__ == '__main__':
    asyncio.run(main())
