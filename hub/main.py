from contextlib import asynccontextmanager
from fastapi import FastAPI, Query, HTTPException, Depends
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from typing import List, Optional
from datetime import datetime
from pathlib import Path
import os
from shared.logger import configure_logging
import logging
from fastapi.responses import JSONResponse

os.environ.setdefault("PEKNO_SERVICE", "hub")
configure_logging()

from hub.core.search import SearchService
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from hub.api.schemas import FrontendSearchItem, SyncRequest
from shared.config import ConfigManager, ConfigKeys
from sqlalchemy import select, delete
from shared.plugins.manager import plugin_manager
from hub.core.security import get_current_user
from hub.core.init_db import ensure_runtime_environment
from shared.api_errors import ApiError
from shared.error_codes import ERR_INTERNAL_SERVER_ERROR, ERR_VALIDATION_FAILED, resolve_error_code_and_detail

from hub.core.media.checker import check_media_dependencies
logger = logging.getLogger("Pekno-Hub")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """系统启动时动态加载插件以及执行环境巡检"""
    check_media_dependencies()
    await ensure_runtime_environment()
    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)
    yield

app = FastAPI(title="Pekno", lifespan=lifespan)

# 跨域配置（开发前端 Vue/React 时必开）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

search_service = SearchService()


async def _get_user_item_state_map(user_id: str, item_ids: list[str]) -> dict[str, UserItemStateORM]:
    if not item_ids:
        return {}
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserItemStateORM).where(
                UserItemStateORM.user_id == user_id,
                UserItemStateORM.item_id.in_(item_ids),
            )
        )
        rows = result.scalars().all()
    return {row.item_id: row for row in rows}


def _build_local_asset_url(local_asset_path: str | None) -> str | None:
    if not local_asset_path:
        return None
    try:
        path = Path(local_asset_path).resolve()
        vault_root = Path("data/vault").resolve()
        try:
            relative = path.relative_to(vault_root)
            return f"/api/static/vault/{relative.as_posix().lstrip('/')}"
        except Exception:
            uploads_root = Path("data/uploads").resolve()
            relative = path.relative_to(uploads_root)
            if relative.parts and relative.parts[0] == "vault":
                return None
            return f"/uploads/{relative.as_posix().lstrip('/')}"
    except Exception:
        return None

from hub.api import data
from hub.api.routers import admin, annotations, auth, items, monitor, notifications, plugins, user_credentials, vault
from hub.api.mcp import mcp_app
from hub.api.middlewares.mcp_auth import MCPAuthMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

# 确保存储目录存在并挂载静态目录，专门用于对外暴露关键帧等媒体素材
os.makedirs(os.path.join("data", "static", "keyframes"), exist_ok=True)
os.makedirs(os.path.join("data", "uploads"), exist_ok=True)
os.makedirs(os.path.join("data", "vault"), exist_ok=True)
os.makedirs(os.path.join("data", "logs"), exist_ok=True)
class CachedStaticFiles(StaticFiles):
    def file_response(self, full_path, stat_result, scope, status_code=200) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
        return response

app.mount("/api/static/vault", CachedStaticFiles(directory="data/vault"), name="vault-static")
app.mount("/api/static", CachedStaticFiles(directory="data/static"), name="static")
app.mount("/uploads", CachedStaticFiles(directory="data/uploads"), name="uploads")

app.include_router(data.router, prefix="/api")
app.include_router(plugins.router)
app.include_router(auth.router)
app.include_router(items.router)
app.include_router(annotations.router)
app.include_router(vault.router)
app.include_router(notifications.router)
app.include_router(user_credentials.router)
app.include_router(admin.router)
app.include_router(monitor.router)
protected_mcp_app = MCPAuthMiddleware(mcp_app)
app.mount("/api/mcp", protected_mcp_app)


@app.exception_handler(ApiError)
async def handle_api_error(_, exc: ApiError):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": exc.error_code,
            "detail": exc.detail,
        },
    )


@app.exception_handler(HTTPException)
async def handle_http_exception(_, exc: HTTPException):
    error_code, detail = resolve_error_code_and_detail(exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error_code": error_code,
            "detail": detail,
        },
        headers=exc.headers,
    )


@app.exception_handler(RequestValidationError)
async def handle_validation_exception(_, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "error_code": ERR_VALIDATION_FAILED,
            "detail": "Request validation failed.",
            "errors": exc.errors(),
        },
    )


@app.exception_handler(Exception)
async def handle_unexpected_exception(_, exc: Exception):
    logger.exception("Unhandled application exception.")
    return JSONResponse(
        status_code=500,
        content={
            "error_code": ERR_INTERNAL_SERVER_ERROR,
            "detail": "An internal server error occurred.",
        },
    )


@app.get("/api/search", response_model=List[FrontendSearchItem])
async def hybrid_search_api(
    q: Optional[str] = Query(None, description="搜索关键词，为空则返回所有"),
    source_type: Optional[str] = Query(None, description="按信息源过滤"),
    favorited_only: bool = Query(False, description="仅搜索当前用户已收藏内容"),
    current_user=Depends(get_current_user),
):
    """
    全局混合搜索接口（语义+关键词）
    
    返回格式匹配前端需求：
    - title: 项目标题
    - summary: 项目描述
    - score: 搜索时返回 0..1 相关性分数；默认时间线为空
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
            state_map = await _get_user_item_state_map(current_user["id"], [item.id for item in items])
            # 转换为前端格式
            search_results = []
            for item in items:
                state = state_map.get(item.id)
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
                    "bilibili_subscribed": "bilibili",
                    "article": "article",
                    "upload": "upload",
                    "arxiv": "arxiv",
                    "youtube": "youtube",
                    "reddit": "reddit",
                    "twitter": "twitter",
                    "mastodon": "mastodon",
                    "bluesky": "bluesky",
                    "notion": "notion",
                    "readwise": "readwise",
                    "pocket": "pocket",
                    "instapaper": "instapaper",
                    "zotero": "zotero",
                    "rss": "rss",
                }
                source = source_map.get(item.source_type, item.source_type)
                
                search_results.append(FrontendSearchItem(
                    id=item.id,
                    title=item.title,
                    summary=summary,
                    long_summary=long_summary,
                    has_long_summary=has_long_summary,
                    cover_url=cover_url,
                    author=author,
                    raw_link=item.raw_link,
                    local_asset_url=_build_local_asset_url(item.local_asset_path),
                    source_type=item.source_type,
                    intent=item.intent,
                    metadata_extra=metadata,
                    score=None,
                    source=source,
                    tags=tags[:5],
                    time=time_str,
                    keyframes=keyframes,
                    is_watch_later=bool(state.is_watch_later) if state else False,
                    is_favorited=bool(state.is_favorited) if state else False,
                ))
            return search_results
    
    # 有搜索词时，执行混合搜索
    results = await search_service.hybrid_search(
        q,
        current_user["id"],
        limit=20,
        source_type=source_type,
        favorited_only=favorited_only,
    )
    state_map = await _get_user_item_state_map(current_user["id"], [item.id for item, _ in results])
    
    search_results = []
    for item, score in results:
        state = state_map.get(item.id)
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
            "bilibili_subscribed": "bilibili",
            "article": "article",
            "upload": "upload",
        }
        source = source_map.get(item.source_type, item.source_type)
        
        # score：RRF 只用于排序；接口返回给前端的是 0..1 相关性分数
        relevance_score = max(0.0, min(1.0, float(score)))
        
        search_results.append(FrontendSearchItem(
            id=item.id,
            title=item.title,
            summary=summary,
            long_summary=long_summary,
            has_long_summary=has_long_summary,
            cover_url=cover_url,
            author=author,
            raw_link=item.raw_link,
            local_asset_url=_build_local_asset_url(item.local_asset_path),
            source_type=item.source_type,
            intent=item.intent,
            metadata_extra=metadata,
            score=round(relevance_score, 4),
            source=source,
            tags=tags[:5],
            time=time_str,
            keyframes=keyframes,
            is_watch_later=bool(state.is_watch_later) if state else False,
            is_favorited=bool(state.is_favorited) if state else False,
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
        state_map = await _get_user_item_state_map(current_user["id"], [item.id for item in items])
        
        # 转换为前端需要的格式，并按 stars 数量排序
        search_results = []
        for item in items:
            state = state_map.get(item.id)
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
                "raw_link": item.raw_link,
                "local_asset_url": _build_local_asset_url(item.local_asset_path),
                "score": round(score, 2),
                "source": "github",
                "tags": tags[:5],  # 最多显示 5 个标签
                "time": time_str,
                "keyframes": keyframes,
                "is_watch_later": bool(state.is_watch_later) if state else False,
                "is_favorited": bool(state.is_favorited) if state else False,
            })
        
        # 按 stars 数量降序排列，然后取 limit 个
        search_results.sort(key=lambda x: x["score"], reverse=True)
        return search_results[:limit]


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


# ========== 配置管理 API: 由通用插件引擎 (/api/plugins) 接管 ==========
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

    # Auto-reload is expensive inside containers because uvicorn falls back to
    # polling the whole application tree. Keep it opt-in via env var.
    reload_enabled = os.getenv("UVICORN_RELOAD", "").strip().lower() in {"1", "true", "yes", "on"}
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=reload_enabled,
        log_config=None,
        access_log=True,
    )
