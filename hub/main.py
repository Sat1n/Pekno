from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
from hub.core.search import SearchService
from hub.core.database import AsyncSessionLocal
from hub.core.database_models import ItemORM
from hub.api.schemas import ItemResponse, SearchResponse, SyncRequest, FrontendSearchItem
from hub.core.config import ConfigManager, ConfigKeys
from sqlalchemy import select, delete
from pydantic import BaseModel

app = FastAPI(title="Iris Intelligence Hub")

# 跨域配置（开发前端 Vue/React 时必开）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

search_service = SearchService()

# 注册路由
from hub.api import data
app.include_router(data.router, prefix="/api")

@app.get("/api/items")
async def get_items(limit: int = 20, offset: int = 0):
    """获取所有已入库的条目列表"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM).order_by(ItemORM.created_at.desc()).offset(offset).limit(limit)
        )
        items = result.scalars().all()
        return items


@app.get("/api/search", response_model=List[FrontendSearchItem])
async def hybrid_search_api(
    q: Optional[str] = Query(None, description="搜索关键词，为空则返回所有")
):
    """
    全局混合搜索接口（语义+关键词）
    
    返回格式匹配前端需求：
    - title: 项目标题
    - summary: 项目描述
    - score: 匹配度分数
    - source: 来源
    - tags: 标签列表
    - time: 时间描述
    """
    # 如果没有搜索词，返回最近的数据
    if not q:
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ItemORM).order_by(ItemORM.created_at.desc()).limit(20)
            )
            items = result.scalars().all()
            # 转换为前端格式
            search_results = []
            for idx, item in enumerate(items):
                metadata = item.metadata_extra or {}
                lang = metadata.get("lang")
                pushed_at = metadata.get("pushed_at")
                
                tags = list(item.tags) if item.tags else []
                if lang and lang not in tags:
                    tags.insert(0, lang)
                if not tags:
                    tags = ["未分类"]
                
                summary = item.summary or item.content_text or "暂无描述"
                time_str = format_github_time(pushed_at) if pushed_at else format_time_ago(item.created_at)
                cover_url = metadata.get("cover_url")
                has_long_summary = metadata.get("has_long_summary", False)
                long_summary = metadata.get("long_summary")
                
                source_map = {
                    "github_star": "github",
                    "bilibili": "bilibili",
                    "article": "article",
                }
                source = source_map.get(item.source_type, item.source_type)
                
                # 默认分数基于排序位置
                score = max(0.5, 1.0 - (idx * 0.05))
                
                search_results.append(FrontendSearchItem(
                    id=item.id,
                    title=item.title,
                    summary=summary,
                    long_summary=long_summary,
                    has_long_summary=has_long_summary,
                    cover_url=cover_url,
                    score=round(score, 2),
                    source=source,
                    tags=tags[:5],
                    time=time_str
                ))
            return search_results
    
    # 有搜索词时，执行混合搜索
    results = await search_service.hybrid_search(q, limit=20)
    
    search_results = []
    for item, v_score, t_score in results:
        # 提取 metadata_extra 中的信息
        metadata = item.metadata_extra or {}
        lang = metadata.get("lang")
        pushed_at = metadata.get("pushed_at")
        
        # 构建 tags：包含语言和原有标签
        tags = list(item.tags) if item.tags else []
        if lang and lang not in tags:
            tags.insert(0, lang)
        if not tags:
            tags = ["未分类"]
        
        # summary：优先使用 AI 生成的摘要，否则使用原始描述
        summary = item.summary or item.content_text or "暂无描述"
        
        # time：使用 pushed_at 或 created_at
        time_str = format_github_time(pushed_at) if pushed_at else format_time_ago(item.created_at)
        
        # cover_url: 获取封面图链接
        cover_url = metadata.get("cover_url")
        
        # has_long_summary: 获取 AI 长摘要缓存标识
        has_long_summary = metadata.get("has_long_summary", False)
        long_summary = metadata.get("long_summary")
        
        # source：根据 source_type 映射
        source_map = {
            "github_star": "github",
            "bilibili": "bilibili",
            "article": "article",
        }
        source = source_map.get(item.source_type, item.source_type)
        
        # score：向量分数 + 文本分数
        score = float(v_score + t_score)
        
        search_results.append(FrontendSearchItem(
            id=item.id,
            title=item.title,
            summary=summary,
            long_summary=long_summary,
            has_long_summary=has_long_summary,
            cover_url=cover_url,
            score=round(score, 2),
            source=source,
            tags=tags[:5],
            time=time_str
        ))
    
    return search_results


@app.get("/api/search/github", response_model=List[FrontendSearchItem])
async def search_github_items(
    q: Optional[str] = Query(None, description="搜索关键词，为空则返回所有"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制")
):
    """
    搜索 GitHub 数据接口
    
    返回格式匹配前端需求：
    - title: 项目标题
    - summary: 项目描述（优先使用 AI 摘要，否则使用原始描述）
    - score: 匹配度分数（基于 stars 数量）
    - source: 来源（统一为 "github"）
    - tags: 标签列表（包含编程语言）
    - time: 仓库最后推送时间
    """
    async with AsyncSessionLocal() as session:
        # 查询 GitHub 来源的数据
        query = select(ItemORM).where(ItemORM.source_type == "github_star")
        
        if q:
            # 如果有搜索词，添加标题和摘要的模糊搜索
            query = query.where(
                (ItemORM.title.ilike(f"%{q}%")) | 
                (ItemORM.summary.ilike(f"%{q}%")) |
                (ItemORM.content_text.ilike(f"%{q}%"))
            )
        
        result = await session.execute(query)
        items = result.scalars().all()
        
        # 转换为前端需要的格式，并按 stars 数量排序
        search_results = []
        for item in items:
            # 提取 metadata_extra 中的信息
            metadata = item.metadata_extra or {}
            stars = metadata.get("stars", 0)
            lang = metadata.get("lang")
            pushed_at = metadata.get("pushed_at")
            
            # 构建 tags：包含语言和原有标签
            tags = list(item.tags) if item.tags else []
            if lang and lang not in tags:
                tags.insert(0, lang)  # 将语言放在最前面
            if not tags:
                tags = ["GitHub"]
            
            # summary：优先使用 AI 生成的摘要，否则使用原始描述
            summary = item.summary or item.content_text or "暂无描述"
            
            # time：使用 pushed_at（仓库最后更新时间）
            time_str = format_github_time(pushed_at) if pushed_at else "未知时间"
            
            # cover_url: 提取封面图链接
            cover_url = metadata.get("cover_url")
            
            # score：基于 stars 数量计算（最多 1.0，最少 0.5）
            score = min(1.0, max(0.5, 0.5 + (stars / 10000)))
            
            # has_long_summary: 获取 AI 长摘要缓存标识
            has_long_summary = metadata.get("has_long_summary", False)
            long_summary = metadata.get("long_summary")

            search_results.append({
                "id": item.id,
                "title": item.title,
                "summary": summary,
                "long_summary": long_summary,
                "has_long_summary": has_long_summary,
                "cover_url": cover_url,
                "score": round(score, 2),
                "source": "github",
                "tags": tags[:5],  # 最多显示 5 个标签
                "time": time_str
            })
        
        # 按 stars 数量降序排列，然后取 limit 个
        search_results.sort(key=lambda x: x["score"], reverse=True)
        return search_results[:limit]


@app.post("/api/sync/github")
async def trigger_github_sync(req: SyncRequest):
    """手动触发 GitHub 同步任务"""
    # 这里我们会调用之前写的 worker/plugins/github/task.py 逻辑
    # 实际生产中这里应该是异步触发，不等待完成即返回 202
    from worker.broker import broker
    from worker.plugins.github.task import sync_github_stars_task
    await sync_github_stars_task.kiq(limit=req.limit if req.limit else 10)
    return {"status": "accepted"}


@app.delete("/api/items/{item_id}")
async def delete_item(item_id: str):
    """手动删除某条数据"""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(delete(ItemORM).where(ItemORM.id == item_id))
    return {"status": "success"}


@app.post("/api/items/{item_id}/summarize")
async def summarize_item(item_id: str):
    """
    触发 AI 总结任务
    
    异步处理，返回 202 Accepted 和 task_id
    """
    # 触发异步任务
    from worker.plugins.github.task import summarize_repo_task
    
    # 生成 task_id
    import uuid
    task_id = str(uuid.uuid4())
    
    # 异步触发总结任务
    await summarize_repo_task.kiq(item_id, task_id)
    
    # 返回 202 Accepted
    return {
        "status": "accepted",
        "task_id": task_id,
        "message": "AI 总结任务已启动，请稍后查询结果"
    }


@app.get("/api/items/{item_id}/summary_status")
async def get_item_summary_status(item_id: str):
    """
    查询某条目的 AI 总结状态
    
    直接从数据库读取 has_long_summary 标识来判断是否完成
    """
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            ItemORM.__table__.select().where(ItemORM.id == item_id)
        )
        item = result.fetchone()
        
        if not item:
            return {"item_id": item_id, "status": "not_found"}
        
        metadata = item.metadata_extra or {}
        has_long_summary = metadata.get("has_long_summary", False)
        
        if has_long_summary:
            return {
                "item_id": item_id,
                "status": "completed",
                "summary": item.summary
            }
        else:
            return {
                "item_id": item_id,
                "status": "pending"
            }


# ========== 配置管理 API ==========

class GitHubConfigRequest(BaseModel):
    token: Optional[str] = None
    sync_limit: int = 100
    auto_sync: bool = False
    auto_sync_interval: int = 60  # 分钟
    auto_summarize: bool = False


class GitHubConfigResponse(BaseModel):
    has_token: bool
    sync_limit: int
    auto_sync: bool
    auto_sync_interval: int
    auto_summarize: bool
    token_preview: Optional[str] = None

class GitHubSyncStatusResponse(BaseModel):
    status: str  # "idle" or "running"
    last_sync_time: Optional[str] = None


@app.get("/api/config/github", response_model=GitHubConfigResponse)
async def get_github_config():
    """
    获取 GitHub 配置
    
    返回当前 GitHub 配置（Token 会隐藏）
    """
    token = await ConfigManager.get_config(ConfigKeys.GITHUB_TOKEN)
    sync_limit = await ConfigManager.get_config(ConfigKeys.GITHUB_SYNC_LIMIT)
    auto_sync = await ConfigManager.get_config(ConfigKeys.GITHUB_AUTO_SYNC)
    auto_sync_interval = await ConfigManager.get_config(ConfigKeys.GITHUB_AUTO_SYNC_INTERVAL)
    auto_summarize = await ConfigManager.get_config(ConfigKeys.GITHUB_AUTO_SUMMARIZE)
    
    # Token 预览：只显示前 4 位
    token_preview = None
    if token and len(token) > 4:
        token_preview = token[:4] + "****"
    
    return GitHubConfigResponse(
        has_token=bool(token),
        sync_limit=int(sync_limit) if sync_limit else 100,
        auto_sync=auto_sync == "true" if auto_sync else False,
        auto_sync_interval=int(auto_sync_interval) if auto_sync_interval else 60,
        auto_summarize=auto_summarize == "true" if auto_summarize else False,
        token_preview=token_preview
    )


@app.post("/api/config/github")
async def save_github_config(config: GitHubConfigRequest):
    """
    保存 GitHub 配置
    
    保存 GitHub Token 和相关设置
    如果提供了新token则更新，否则保留原有token
    """
    # 如果提供了新token，则保存
    if config.token:
        success = await ConfigManager.set_config(
            ConfigKeys.GITHUB_TOKEN,
            config.token,
            description="GitHub Personal Access Token"
        )
        
        if not success:
            raise HTTPException(status_code=500, detail="保存 Token 失败")
    
    # 保存同步限制
    await ConfigManager.set_config(
        ConfigKeys.GITHUB_SYNC_LIMIT,
        str(config.sync_limit),
        description="GitHub 同步仓库数量限制"
    )
    
    # 保存自动同步设置
    await ConfigManager.set_config(
        ConfigKeys.GITHUB_AUTO_SYNC,
        "true" if config.auto_sync else "false",
        description="是否自动同步 GitHub Star"
    )
    
    # 保存自动同步时间间隔
    await ConfigManager.set_config(
        ConfigKeys.GITHUB_AUTO_SYNC_INTERVAL,
        str(config.auto_sync_interval),
        description="GitHub 自动同步间隔时间 (分钟)"
    )
    
    # 保存是否自动生成 AI 短摘要
    await ConfigManager.set_config(
        ConfigKeys.GITHUB_AUTO_SUMMARIZE,
        "true" if config.auto_summarize else "false",
        description="是否自动生成 AI 短摘要"
    )
    
    # 若保存了配置且开启自动同步，可以尝试立即出发一次
    if config.auto_sync and config.token:
        from worker.plugins.github.task import sync_github_stars_task
        await sync_github_stars_task.kiq(limit=config.sync_limit)
    
    return {
        "status": "success",
        "message": "GitHub 配置已保存"
    }

@app.get("/api/config/github/status", response_model=GitHubSyncStatusResponse)
async def get_github_sync_status():
    """获取当前 GitHub Sync 状态"""
    status = await ConfigManager.get_config(ConfigKeys.GITHUB_SYNC_STATUS)
    last_sync = await ConfigManager.get_config(ConfigKeys.GITHUB_LAST_SYNC_TIME)
    return GitHubSyncStatusResponse(
        status=status if status else "idle",
        last_sync_time=last_sync
    )


@app.post("/api/config/github/test")
async def test_github_token():
    """
    测试 GitHub Token 是否有效（轻量级，只获取用户信息）
    
    返回测试结果
    """
    # 使用已保存的token进行测试
    token = await ConfigManager.get_config(ConfigKeys.GITHUB_TOKEN)
    
    if not token:
        raise HTTPException(status_code=400, detail="未配置 GitHub Token")
    
    from worker.plugins.github.client import GitHubClient
    client = GitHubClient(token)
    
    result = await client.test_connection()
    
    if not result.get("valid"):
        raise HTTPException(status_code=401, detail=f"Token 无效: {result.get('error', 'Unknown error')}")
    
    return {
        "status": "success",
        "message": f"连接成功！欢迎，{result.get('name') or result.get('username')}",
        "username": result.get("username"),
    }


@app.delete("/api/config/github")
async def delete_github_config():
    """
    删除 GitHub 配置
    
    清除所有 GitHub 相关配置
    """
    await ConfigManager.delete_config(ConfigKeys.GITHUB_TOKEN)
    await ConfigManager.delete_config(ConfigKeys.GITHUB_SYNC_LIMIT)
    await ConfigManager.delete_config(ConfigKeys.GITHUB_AUTO_SYNC)
    await ConfigManager.delete_config(ConfigKeys.GITHUB_AUTO_SYNC_INTERVAL)
    await ConfigManager.delete_config(ConfigKeys.GITHUB_AUTO_SUMMARIZE)
    
    return {
        "status": "success",
        "message": "GitHub 配置已清除"
    }


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


def format_github_time(time_str: str) -> str:
    """格式化 GitHub 时间字符串为相对描述"""
    if not time_str:
        return "未知时间"
    
    try:
        # GitHub API 返回格式: "2023-10-15T12:30:00Z"
        dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
        # 转换为本地时间（去掉时区信息）
        dt = dt.replace(tzinfo=None)
        return format_time_ago(dt)
    except:
        return "未知时间"


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True)
