from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
from hub.core.search import SearchService
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from hub.api.schemas import FrontendSearchItem, SyncRequest
from shared.config import ConfigManager, ConfigKeys
from sqlalchemy import select, delete
from shared.plugins.manager import plugin_manager
from hub.core.security import get_current_user
from hub.core.init_db import ensure_runtime_tables

from hub.core.media.checker import check_media_dependencies

@asynccontextmanager
async def lifespan(app: FastAPI):
    """系统启动时动态加载插件以及执行环境巡检"""
    check_media_dependencies()
    await ensure_runtime_tables()
    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)
    yield

app = FastAPI(title="Iris Intelligence Hub", lifespan=lifespan)

# 跨域配置（开发前端 Vue/React 时必开）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

search_service = SearchService()

from hub.api import data
from hub.api.routers import admin, auth, items, plugins
from hub.api.mcp import mcp_app
from hub.api.middlewares.mcp_auth import MCPAuthMiddleware
import os
from fastapi.staticfiles import StaticFiles

# 确保存储目录存在并挂载静态目录，专门用于对外暴露关键帧等媒体素材
os.makedirs(os.path.join("data", "static", "keyframes"), exist_ok=True)
app.mount("/api/static", StaticFiles(directory="data/static"), name="static")

app.include_router(data.router, prefix="/api")
app.include_router(plugins.router)
app.include_router(auth.router)
app.include_router(items.router)
app.include_router(admin.router)
protected_mcp_app = MCPAuthMiddleware(mcp_app)
app.mount("/api/mcp", protected_mcp_app)


@app.get("/api/search", response_model=List[FrontendSearchItem])
async def hybrid_search_api(
    q: Optional[str] = Query(None, description="搜索关键词，为空则返回所有"),
    source_type: Optional[str] = Query(None, description="按信息源过滤"),
    current_user=Depends(get_current_user),
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
                select(ItemORM)
                .join(UserItemStateORM, UserItemStateORM.item_id == ItemORM.id)
                .where(UserItemStateORM.user_id == current_user["id"])
                .order_by(ItemORM.created_at.desc())
                .limit(20)
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
                
                # 强制卡片的 summary 只使用原始短描述
                summary = item.content_text or "暂无描述"
                time_str = format_github_time(pushed_at) if pushed_at else format_time_ago(item.created_at)
                cover_url = metadata.get("cover_url")
                author = metadata.get("up_name") or metadata.get("author")
                has_long_summary = metadata.get("has_long_summary", False)
                # 长总结独立赋值 (item.summary 里面存的才是大模型生成的 Markdown)
                long_summary = metadata.get("long_summary") if has_long_summary else None
                keyframes = metadata.get("keyframes")
                
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
                    author=author,
                    score=round(score, 2),
                    source=source,
                    tags=tags[:5],
                    time=time_str,
                    keyframes=keyframes
                ))
            return search_results
    
    # 有搜索词时，执行混合搜索
    results = await search_service.hybrid_search(q, current_user["id"], limit=20, source_type=source_type)
    
    search_results = []
    for item, score in results:
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
        
        # 强制卡片的 summary 只使用原始短描述
        summary = item.content_text or "暂无描述"
        
        # time：使用 pushed_at 或 created_at
        time_str = format_github_time(pushed_at) if pushed_at else format_time_ago(item.created_at)
        
        # cover_url: 获取封面图链接
        cover_url = metadata.get("cover_url")
        author = metadata.get("up_name") or metadata.get("author")
        
        # has_long_summary: 获取 AI 长摘要缓存标识
        has_long_summary = metadata.get("has_long_summary", False)
        # 长总结独立赋值 (item.summary 里面存的才是大模型生成的 Markdown)
        long_summary = metadata.get("long_summary") if has_long_summary else None
        keyframes = metadata.get("keyframes")
        
        # source：根据 source_type 映射
        source_map = {
            "github_star": "github",
            "bilibili": "bilibili",
            "article": "article",
        }
        source = source_map.get(item.source_type, item.source_type)
        
        # score：向量分数 + 文本分数
        score = round(float(score), 4)
        
        search_results.append(FrontendSearchItem(
            id=item.id,
            title=item.title,
            summary=summary,
            long_summary=long_summary,
            has_long_summary=has_long_summary,
            cover_url=cover_url,
            author=author,
            score=round(score, 2),
            source=source,
            tags=tags[:5],
            time=time_str,
            keyframes=keyframes
        ))
    
    return search_results


@app.get("/api/search/github", response_model=List[FrontendSearchItem])
async def search_github_items(
    q: Optional[str] = Query(None, description="搜索关键词，为空则返回所有"),
    limit: int = Query(20, ge=1, le=100, description="返回数量限制"),
    current_user=Depends(get_current_user),
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
        query = query.join(UserItemStateORM, UserItemStateORM.item_id == ItemORM.id).where(
            UserItemStateORM.user_id == current_user["id"]
        )
        
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
            
            # 强制卡片的 summary 只使用原始短描述
            summary = item.content_text or "暂无描述"
            
            # time：使用 pushed_at（仓库最后更新时间）
            time_str = format_github_time(pushed_at) if pushed_at else "未知时间"
            
            # cover_url: 提取封面图链接
            cover_url = metadata.get("cover_url")
            author = metadata.get("up_name") or metadata.get("author")
            
            # score：基于 stars 数量计算（最多 1.0，最少 0.5）
            score = min(1.0, max(0.5, 0.5 + (stars / 10000)))
            
            # has_long_summary: 获取 AI 长摘要缓存标识
            has_long_summary = metadata.get("has_long_summary", False)
            # 长总结独立赋值 (item.summary 里面存的才是大模型生成的 Markdown)
            long_summary = metadata.get("long_summary") if has_long_summary else None
            keyframes = metadata.get("keyframes")

            search_results.append({
                "id": item.id,
                "title": item.title,
                "summary": summary,
                "long_summary": long_summary,
                "has_long_summary": has_long_summary,
                "cover_url": cover_url,
                "author": author,
                "score": round(score, 2),
                "source": "github",
                "tags": tags[:5],  # 最多显示 5 个标签
                "time": time_str,
                "keyframes": keyframes
            })
        
        # 按 stars 数量降序排列，然后取 limit 个
        search_results.sort(key=lambda x: x["score"], reverse=True)
        return search_results[:limit]


# ========== 配置管理 API: 由通用插件引擎 (/api/plugins) 接管 ==========
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
