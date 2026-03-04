from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
from hub.core.search import SearchService
from hub.core.database import AsyncSessionLocal
from hub.core.database_models import ItemORM
from hub.api.schemas import ItemResponse, SearchResponse, SyncRequest, FrontendSearchItem
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
    """混合搜索接口（语义+关键词）"""
    results = await search_service.hybrid_search(q, limit=10)
    # 转换为 SearchResponse 格式
    return [
        {**item.__dict__, "score": score} 
        for item, score in results
    ]


@app.get("/api/search/github", response_model=List[FrontendSearchItem])
async def search_github_items(
    q: Optional[str] = Query(None, description="搜索关键词，为空则返回所有"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制")
):
    """
    搜索 GitHub 数据接口
    
    返回格式匹配前端需求：
    - title: 项目标题
    - summary: 项目描述
    - score: 匹配度分数（0-1）
    - source: 来源（固定为 "github"）
    - tags: 标签列表
    - time: 时间描述
    """
    async with AsyncSessionLocal() as session:
        # 查询 GitHub 来源的数据
        query = select(ItemORM).where(ItemORM.source_type == "github_star")
        
        if q:
            # 如果有搜索词，添加标题和摘要的模糊搜索
            query = query.where(
                (ItemORM.title.ilike(f"%{q}%")) | 
                (ItemORM.summary.ilike(f"%{q}%"))
            )
        
        # 按创建时间倒序排列
        query = query.order_by(ItemORM.created_at.desc()).limit(limit)
        
        result = await session.execute(query)
        items = result.scalars().all()
        
        # 转换为前端需要的格式
        search_results = []
        for idx, item in enumerate(items):
            # 计算时间描述
            time_desc = format_time_ago(item.created_at)
            
            # 计算分数（基于排序位置，越新的分数越高）
            score = max(0.5, 1.0 - (idx * 0.05))
            
            search_results.append(FrontendSearchItem(
                title=item.title,
                summary=item.summary or "暂无描述",
                score=round(score, 2),
                source="github",
                tags=item.tags or ["GitHub"],
                time=time_desc
            ))
        
        return search_results


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


def format_time_ago(dt: datetime) -> str:
    """格式化时间为相对描述"""
    now = datetime.now()
    diff = now - dt
    
    if diff.days == 0:
        hours = diff.seconds // 3600
        if hours == 0:
            minutes = diff.seconds // 60
            if minutes == 0:
                return "刚刚"
            return f"{minutes}分钟前"
        return f"{hours}小时前"
    elif diff.days == 1:
        return "昨天"
    elif diff.days < 7:
        return f"{diff.days}天前"
    elif diff.days < 30:
        weeks = diff.days // 7
        return f"{weeks}周前"
    elif diff.days < 365:
        months = diff.days // 30
        return f"{months}个月前"
    else:
        years = diff.days // 365
        return f"{years}年前"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)