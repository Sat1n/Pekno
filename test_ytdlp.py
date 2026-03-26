import asyncio
import sys
import json
sys.path.append(r'F:\Cardinal\Pekno')
from hub.core.media.downloader import YTDlpService

async def main():
    item_url = "https://www.bilibili.com/video/BV1vA411b7ip"
    
    # We will test extract_info
    print(f"Testing YTDlp extraction on: {item_url}")
    info = await asyncio.to_thread(YTDlpService.extract_info, item_url, None)
    
    print(f"Extract Info Output:")
    print(f"Duration: {info.get('duration')} seconds")
    print(f"Resolution: {info.get('resolution')}")
    print(f"Ext: {info.get('ext')}")
    
if __name__ == '__main__':
    asyncio.run(main())
