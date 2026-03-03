import asyncio
from worker.broker import broker
from hub.core.models import UniversalItem, ItemIntent

async def send_mock_task():
    # 模拟 Hub 发送一个任务
    mock_item = {
        "id": "test_001",
        "title": "来自 Redis 的问候",
        "source_type": "manual",
        "raw_link": "https://example.com",
        "intent": "article",
        "capabilities": ["summarize"]
    }
    
    print("正在向 Redis 发送任务...")
    # 找到任务并推入队列
    from worker.ingestion.pipeline import process_new_item_task
    await process_new_item_task.kiq(mock_item)
    print("任务已发出！请去 Worker 终端查看日志。")

if __name__ == "__main__":
    asyncio.run(send_mock_task())