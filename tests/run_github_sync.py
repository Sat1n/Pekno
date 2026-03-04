import asyncio
from worker.plugins.github.task import sync_github_stars_task

async def test_sync():
    # 填入你的 Token
    MY_TOKEN = "GITHUB_TOKEN_PLACEHOLDER" 
    # 运行同步（只抓最近 5 个，别让 Ollama 冒烟了）
    await sync_github_stars_task(MY_TOKEN, limit=5)

if __name__ == "__main__":
    asyncio.run(test_sync())