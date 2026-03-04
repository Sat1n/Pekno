from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from hub.core.search import SearchService
from hub.core.database import AsyncSessionLocal
from hub.core.database_models import ItemORM
from hub.api.schemas import ItemResponse, SearchResponse, SyncRequest
from sqlalchemy import select, delete

app = FastAPI(title="Iris Intelligence Hub")

# 跨域配置（开发前端 Vue/React 时必开）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

search_service = SearchService()

@app.get("/api/items")
async def get_items(limit: int = 20, offset: int = 0):
    """获取所有已入库的条目列表"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM).order_by(ItemORM.created_at.desc()).offset(offset).limit(limit)
        )
        items = result.scalars().all()
        return items

@app.get("/api/search", response_model=List[SearchResponse])
async def hybrid_search_api(q: str = Query(..., min_length=1, description="搜索关键词")):
    results = await search_service.hybrid_search(q, limit=10)
    # 转换为 SearchResponse 格式
    return [
        {**item.__dict__, "score": score} 
        for item, score in results
    ]

@app.post("/api/sync/github")
async def trigger_github_sync(req: SyncRequest):
    """手动触发 GitHub 同步任务"""
    # 这里我们会调用之前写的 worker/plugins/github/task.py 逻辑
    # 实际生产中这里应该是异步触发，不等待完成即返回 202
    from worker.plugins.github.task import sync_github_stars_task
    import asyncio
    asyncio.create_task(sync_github_stars_task(req.token, limit=req.limit if req.limit else 10))
    return {"status": "accepted"}

@app.delete("/api/items/{item_id}")
async def delete_item(item_id: str):
    """手动删除某条数据"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(delete(ItemORM).where(ItemORM.id == item_id))
    return {"status": "success"}