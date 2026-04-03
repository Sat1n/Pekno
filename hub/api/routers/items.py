import hashlib
import mimetypes
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert

from hub.api.schemas import ItemResponse, ItemStateResponse, ReadBatchRequest
from shared.config import ConfigManager
from hub.core.security import get_current_user
from shared.database import AsyncSessionLocal
from shared.logger import hub_log
from shared.models import ItemORM, UserItemStateORM, VaultCategoryORM
from shared.plugins.base import BasePlugin
from shared.plugins.manager import plugin_manager
from shared.time_utils import now_in_app_timezone_naive

router = APIRouter(prefix="/api/items", tags=["Items"])

UPLOAD_ROOT = Path("data/uploads")
VAULT_ROOT = Path("data/vault")
SUPPORTED_STATIC_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
SUPPORTED_STATIC_IMAGE_MIME_TYPES = {
    "image/png",
    "image/jpeg",
    "image/webp",
    "image/bmp",
}
UNSUPPORTED_IMAGE_EXTENSIONS = {".gif"}
UNSUPPORTED_IMAGE_MIME_TYPES = {"image/gif"}
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi"}
SUPPORTED_VIDEO_MIME_TYPES = {
    "video/mp4",
    "video/webm",
    "video/quicktime",
    "video/x-matroska",
    "video/x-msvideo",
    "video/mpeg",
}
SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".webm"}
SUPPORTED_AUDIO_MIME_TYPES = {
    "audio/mpeg",
    "audio/mp3",
    "audio/wav",
    "audio/x-wav",
    "audio/mp4",
    "audio/x-m4a",
    "audio/aac",
    "audio/flac",
    "audio/ogg",
    "audio/webm",
}
SUPPORTED_PDF_EXTENSIONS = {".pdf"}
SUPPORTED_PDF_MIME_TYPES = {"application/pdf"}
SUPPORTED_TEXT_EXTENSIONS = {".txt"}
SUPPORTED_TEXT_MIME_TYPES = {"text/plain"}
SUPPORTED_MARKDOWN_EXTENSIONS = {".md", ".markdown"}
SUPPORTED_MARKDOWN_MIME_TYPES = {"text/markdown", "text/x-markdown"}
SUPPORTED_DOCX_EXTENSIONS = {".docx"}
SUPPORTED_DOCX_MIME_TYPES = {
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
UNSUPPORTED_OFFICE_EXTENSIONS = {".doc", ".docm", ".xls", ".xlsx", ".ppt", ".pptx"}
UNSUPPORTED_OFFICE_MIME_KEYWORDS = {
    "officedocument",
    "msword",
    "excel",
    "powerpoint",
    "presentationml",
    "spreadsheetml",
}
SUPPORTED_DOCX_MIME_KEYWORDS = {
    "wordprocessingml.document",
}
PLUGIN_NAME_ALIASES = {
    "github": "github_stars",
    "github_stars": "github_stars",
    "bilibili": "bilibili_sync",
    "bilibili_sync": "bilibili_sync",
}


def _has_unresolved_vault_readme_assets(metadata: Dict[str, Any]) -> bool:
    if metadata.get("vault_readme_asset_failures"):
        return True

    readme_text = str(metadata.get("vault_readme_text") or "")
    if not readme_text:
        return False

    markdown_matches = re.findall(r'!\[[^\]]*\]\(([^)]+)\)', readme_text)
    html_matches = re.findall(r'<img\b[^>]*src=["\']([^"\']+)["\']', readme_text, flags=re.IGNORECASE)
    for asset_url in [*(markdown_matches or []), *(html_matches or [])]:
        normalized = str(asset_url).strip().replace("\\", "/").lower()
        if not normalized:
            continue
        if normalized.startswith("http://") or normalized.startswith("https://") or normalized.startswith("//") or normalized.startswith("data:"):
            continue
        if normalized.startswith("/api/static/vault/"):
            continue
        return True

    return False


class ParseItemRequest(BaseModel):
    plugin_name: str
    url: str
    retention_days: int = -1


class ParsePluginInfo(BaseModel):
    id: str
    name: str
    source_type: str


class AssignVaultCategoryRequest(BaseModel):
    vault_category_id: str | None = None


def _to_item_response(item: ItemORM, state: Optional[UserItemStateORM]) -> ItemResponse:
    metadata = item.metadata_extra or {}
    return ItemResponse(
        id=item.id,
        title=item.title,
        source_type=item.source_type,
        raw_link=item.raw_link,
        content_text=item.content_text,
        summary=item.summary,
        tags=item.tags or [],
        intent=item.intent,
        created_at=item.created_at,
        metadata_extra=metadata,
        local_asset_url=_build_local_asset_url(item.local_asset_path),
        vault_category_id=state.vault_category_id if state else None,
        is_read=bool(state.is_read) if state else False,
        is_watch_later=bool(state.is_watch_later) if state else False,
        is_favorited=bool(state.is_favorited) if state else False,
    )


def _public_upload_path(relative_path: Path) -> str:
    normalized = relative_path.as_posix().lstrip("/")
    return f"/uploads/{normalized}"


def _build_local_asset_url(local_asset_path: Optional[str]) -> Optional[str]:
    if not local_asset_path:
        return None
    try:
        path = Path(local_asset_path).resolve()
        try:
            relative = path.relative_to(VAULT_ROOT.resolve())
            return f"/api/static/vault/{relative.as_posix().lstrip('/')}"
        except Exception:
            relative = path.relative_to(UPLOAD_ROOT.resolve())
            if relative.parts and relative.parts[0] == "vault":
                return None
            return _public_upload_path(relative)
    except Exception:
        return None


def _infer_upload_type(filename: str, content_type: Optional[str]) -> tuple[str, str]:
    guessed_type = content_type or mimetypes.guess_type(filename)[0] or "application/octet-stream"
    if guessed_type.startswith("image/"):
        return "image", guessed_type
    if guessed_type.startswith("video/"):
        return "video", guessed_type
    if guessed_type.startswith("audio/"):
        return "audio", guessed_type
    return "document", guessed_type


def _normalize_upload_mime(filename: str, content_type: Optional[str]) -> str:
    provided = (content_type or "").split(";", 1)[0].strip().lower()
    guessed = (mimetypes.guess_type(filename)[0] or "").split(";", 1)[0].strip().lower()
    return provided or guessed or "application/octet-stream"


def _extract_text_from_upload_bytes(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "gb18030"):
        try:
            return content.decode(encoding).strip()
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="ignore").strip()


def _validate_and_classify_upload(filename: str, content_type: Optional[str]) -> tuple[str, str]:
    ext = Path(filename or "").suffix.lower()
    mime_type = _normalize_upload_mime(filename, content_type)

    if ext in UNSUPPORTED_IMAGE_EXTENSIONS or mime_type in UNSUPPORTED_IMAGE_MIME_TYPES:
        raise HTTPException(status_code=400, detail="GIF 动图暂不支持上传，请改用静态图片格式。")

    if ext in SUPPORTED_STATIC_IMAGE_EXTENSIONS or mime_type in SUPPORTED_STATIC_IMAGE_MIME_TYPES:
        return "image", mime_type

    if mime_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="当前仅支持 PNG、JPG/JPEG、WEBP、BMP 静态图片上传。")

    if ext in SUPPORTED_VIDEO_EXTENSIONS or mime_type in SUPPORTED_VIDEO_MIME_TYPES:
        return "video", mime_type

    if mime_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="当前仅支持 MP4、WEBM、MOV、M4V、MKV、AVI 等常见视频格式。")

    if ext in SUPPORTED_AUDIO_EXTENSIONS or mime_type in SUPPORTED_AUDIO_MIME_TYPES:
        return "audio", mime_type

    if mime_type.startswith("audio/"):
        raise HTTPException(status_code=400, detail="当前仅支持 MP3、WAV、M4A、AAC、FLAC、OGG、WEBM 等常见音频格式。")

    if ext in SUPPORTED_PDF_EXTENSIONS or mime_type in SUPPORTED_PDF_MIME_TYPES:
        return "document", "application/pdf"

    if ext in SUPPORTED_MARKDOWN_EXTENSIONS or mime_type in SUPPORTED_MARKDOWN_MIME_TYPES:
        return "document", "text/markdown"

    if ext in SUPPORTED_TEXT_EXTENSIONS or mime_type in SUPPORTED_TEXT_MIME_TYPES:
        return "document", "text/plain"

    if ext in SUPPORTED_DOCX_EXTENSIONS or mime_type in SUPPORTED_DOCX_MIME_TYPES or any(
        keyword in mime_type for keyword in SUPPORTED_DOCX_MIME_KEYWORDS
    ):
        return "document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    if ext in UNSUPPORTED_OFFICE_EXTENSIONS or any(keyword in mime_type for keyword in UNSUPPORTED_OFFICE_MIME_KEYWORDS):
        raise HTTPException(status_code=400, detail="当前仅支持 DOCX，其他 Office 文档请先转换为 PDF、TXT 或 Markdown。")

    raise HTTPException(status_code=400, detail="当前仅支持静态图片、常见视频音频、PDF、TXT、Markdown 与 DOCX 上传。")


def _is_text_upload_mime(mime_type: str) -> bool:
    normalized = (mime_type or "").strip().lower()
    return (
        normalized in SUPPORTED_TEXT_MIME_TYPES
        or normalized in SUPPORTED_MARKDOWN_MIME_TYPES
        or normalized in SUPPORTED_DOCX_MIME_TYPES
    )


def _is_pdf_item(item: ItemORM) -> bool:
    metadata = item.metadata_extra or {}
    mime_type = str(
        metadata.get("mime_type")
        or metadata.get("vault_download_content_type")
        or ""
    ).lower()
    candidate = str(item.local_asset_path or item.raw_link or "").lower()
    return mime_type == "application/pdf" or candidate.endswith(".pdf")


async def _resolve_plugin(plugin_name: str) -> BasePlugin:
    plugin_id = PLUGIN_NAME_ALIASES.get(plugin_name, plugin_name)
    plugin = plugin_manager.get_plugin(plugin_id)
    if plugin:
        return plugin

    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)

    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"未找到插件: {plugin_name}")
    return plugin


async def _store_user_item(item_data: Dict[str, Any], user_id: str, *, retention_days: int = -1) -> str:
    item_id = str(item_data["id"])
    created_at = now_in_app_timezone_naive()
    metadata_extra = dict(item_data.get("metadata_extra") or {})
    metadata_extra.setdefault("has_long_summary", False)

    summary = item_data.get("summary") or item_data.get("content_text") or item_data.get("title") or ""

    async with AsyncSessionLocal() as session:
        async with session.begin():
            item_stmt = insert(ItemORM).values(
                id=item_id,
                title=item_data.get("title", ""),
                source_type=item_data.get("source_type", "upload"),
                raw_link=item_data.get("raw_link", "#"),
                content_text=item_data.get("content_text") or "",
                summary=summary,
                tags=item_data.get("tags") or [],
                intent=item_data.get("intent", "article"),
                created_at=created_at,
                updated_at=created_at,
                retention_days=retention_days,
                metadata_extra=metadata_extra,
                file_hash=item_data.get("file_hash"),
                local_asset_path=item_data.get("local_asset_path"),
            ).on_conflict_do_update(
                index_elements=["id"],
                set_={
                    "title": item_data.get("title", ""),
                    "source_type": item_data.get("source_type", "upload"),
                    "raw_link": item_data.get("raw_link", "#"),
                    "content_text": item_data.get("content_text") or "",
                    "summary": summary,
                    "tags": item_data.get("tags") or [],
                    "intent": item_data.get("intent", "article"),
                    "updated_at": created_at,
                    "retention_days": retention_days,
                    "metadata_extra": metadata_extra,
                    "file_hash": item_data.get("file_hash"),
                    "local_asset_path": item_data.get("local_asset_path"),
                },
            )
            await session.execute(item_stmt)

            state_stmt = insert(UserItemStateORM).values(
                user_id=user_id,
                item_id=item_id,
                vault_category_id=None,
                is_read=False,
                is_watch_later=False,
                is_favorited=False,
                updated_at=created_at,
            ).on_conflict_do_nothing(index_elements=["user_id", "item_id"])
            await session.execute(state_stmt)

    return item_id


async def _fetch_item_for_user(item_id: str, user_id: str) -> tuple[ItemORM, UserItemStateORM]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM, UserItemStateORM)
            .join(
                UserItemStateORM,
                and_(
                    UserItemStateORM.item_id == ItemORM.id,
                    UserItemStateORM.user_id == user_id,
                ),
            )
            .where(ItemORM.id == item_id)
        )
        row = result.first()
    if not row:
        raise HTTPException(status_code=404, detail="找不到对应条目")
    return row


async def _ensure_user_item_state(
    user_id: str,
    item_id: str,
    *,
    is_watch_later: Optional[bool] = None,
    is_favorited: Optional[bool] = None,
) -> UserItemStateORM:
    now = now_in_app_timezone_naive()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.user_id == user_id,
                    UserItemStateORM.item_id == item_id,
                )
            )
            state = result.scalar_one_or_none()
            if state is None:
                state_stmt = insert(UserItemStateORM).values(
                    user_id=user_id,
                    item_id=item_id,
                    vault_category_id=None,
                    is_read=False,
                    is_watch_later=bool(is_watch_later),
                    is_favorited=bool(is_favorited),
                    updated_at=now,
                ).on_conflict_do_nothing(index_elements=["user_id", "item_id"])
                await session.execute(state_stmt)
            else:
                if is_watch_later is not None:
                    state.is_watch_later = is_watch_later
                if is_favorited is not None:
                    state.is_favorited = is_favorited
                state.updated_at = now

    _, refreshed_state = await _fetch_item_for_user(item_id, user_id)
    return refreshed_state


async def _queue_vault_download_if_needed(item_id: str, item: ItemORM, user_id: str | None = None):
    local_asset_path = item.local_asset_path
    metadata = item.metadata_extra or {}
    needs_github_readme_backfill = (
        item.source_type == "github_star"
        and (
            not metadata.get("vault_readme_text")
            or not metadata.get("vault_readme_assets_localized")
            or _has_unresolved_vault_readme_assets(metadata)
        )
    )
    if item.source_type == "upload":
        return
    if local_asset_path and Path(local_asset_path).exists() and not needs_github_readme_backfill:
        return

    try:
        from worker.tasks import task_download_vault_asset

        await task_download_vault_asset.kiq(item_id, user_id)
        hub_log.info(f"📨 已投递 Vault 资源补齐任务: {item_id} | user={user_id or 'fallback'}")
    except Exception:
        hub_log.exception("投递 Vault 下载任务失败")


@router.post("/{item_id}/ensure_vault_asset", response_model=ItemResponse)
async def ensure_vault_asset(item_id: str, current_user=Depends(get_current_user)):
    item, state = await _fetch_item_for_user(item_id, current_user["id"])
    await _queue_vault_download_if_needed(item_id, item, current_user["id"])
    return _to_item_response(item, state)


async def _queue_video_summary_if_needed(item: ItemORM):
    if item.intent != "video":
        return

    metadata = item.metadata_extra or {}
    if metadata.get("has_long_summary") or metadata.get("raw_transcript"):
        return

    try:
        from worker.tasks import process_multimedia_task

        await process_multimedia_task.kiq(item.id, item.raw_link)
    except Exception:
        hub_log.exception("投递视频总结任务失败")


async def _queue_image_summary_if_needed(item: ItemORM):
    if item.intent != "image":
        return

    metadata = item.metadata_extra or {}
    if metadata.get("has_long_summary") and metadata.get("image_understanding"):
        return

    try:
        from worker.tasks import process_image_understanding_task

        await process_image_understanding_task.kiq(item.id)
    except Exception:
        hub_log.exception("投递图片理解任务失败")


async def _queue_text_processing_if_needed(item: ItemORM):
    metadata = item.metadata_extra or {}
    mime_type = str(metadata.get("mime_type") or "").lower()
    if not _is_text_upload_mime(mime_type):
        return

    if item.embedding is not None and item.tags:
        return

    try:
        from worker.tasks import process_uploaded_text_document_task

        await process_uploaded_text_document_task.kiq(item.id)
    except Exception:
        hub_log.exception("投递文本上传分析任务失败")


async def _queue_pdf_ocr_if_needed(item: ItemORM):
    if not _is_pdf_item(item):
        return

    metadata = item.metadata_extra or {}
    ocr_meta = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
    if ocr_meta.get("status") in {"processing", "completed"}:
        return
    if not item.local_asset_path or not Path(item.local_asset_path).exists():
        return

    try:
        from worker.tasks import process_pdf_ocr_task

        await process_pdf_ocr_task.kiq(item.id)
    except Exception:
        hub_log.exception("投递 PDF OCR 任务失败")


@router.get("", response_model=List[ItemResponse])
async def get_items(
    limit: Optional[int] = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    watch_later_only: bool = Query(default=False),
    favorited_only: bool = Query(default=False),
    source_type: Optional[str] = Query(default=None),
    current_user=Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ItemORM, UserItemStateORM)
            .join(
                UserItemStateORM,
                and_(
                    UserItemStateORM.item_id == ItemORM.id,
                    UserItemStateORM.user_id == current_user["id"],
                ),
            )
            .order_by(ItemORM.created_at.desc())
            .offset(offset)
        )
        if watch_later_only:
            stmt = stmt.where(UserItemStateORM.is_watch_later == True)
        if favorited_only:
            stmt = stmt.where(UserItemStateORM.is_favorited == True)
        if source_type:
            stmt = stmt.where(ItemORM.source_type == source_type)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

    return [_to_item_response(item, state) for item, state in rows]


@router.get("/parse/plugins", response_model=List[ParsePluginInfo])
async def get_parse_plugins(current_user=Depends(get_current_user)):
    if not plugin_manager.plugins:
        async with AsyncSessionLocal() as session:
            await plugin_manager.load_enabled_plugins(session)

    results: List[ParsePluginInfo] = []
    for plugin in plugin_manager.plugins.values():
        manifest = getattr(plugin, "_manifest", {}) or plugin.manifest or {}
        parse_impl = getattr(plugin.__class__, "parse_single_item", None)
        if parse_impl is None or parse_impl is BasePlugin.parse_single_item:
            continue
        results.append(
            ParsePluginInfo(
                id=manifest.get("id", ""),
                name=manifest.get("name", manifest.get("id", "未知插件")),
                source_type=manifest.get("source_type", manifest.get("id", "")),
            )
        )
    return results


@router.post("/upload", response_model=ItemResponse)
async def upload_item(
    file: UploadFile = File(...),
    title: Optional[str] = Form(default=None),
    summary: Optional[str] = Form(default=None),
    retention_days: int = Form(default=-1),
    auto_favorite: bool = Form(default=False),
    current_user=Depends(get_current_user),
):
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

    original_name = file.filename or "upload.bin"
    ext = Path(original_name).suffix
    month_dir = datetime.now().strftime("%Y-%m")
    relative_dir = Path(month_dir)
    target_dir = UPLOAD_ROOT / relative_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    target_name = f"{uuid.uuid4().hex}{ext}"
    target_path = target_dir / target_name

    content = await file.read()
    file_hash = hashlib.sha256(content).hexdigest()

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM).where(ItemORM.file_hash == file_hash)
        )
        existing_item = result.scalar_one_or_none()

    if existing_item:
        if auto_favorite:
            state = await _ensure_user_item_state(
                current_user["id"],
                existing_item.id,
                is_favorited=True,
            )
        else:
            state = await _ensure_user_item_state(current_user["id"], existing_item.id)

        if existing_item.intent == "video":
            await _queue_video_summary_if_needed(existing_item)
        elif existing_item.intent == "image":
            await _queue_image_summary_if_needed(existing_item)
        elif _is_pdf_item(existing_item):
            await _queue_pdf_ocr_if_needed(existing_item)
        else:
            await _queue_text_processing_if_needed(existing_item)

        response_item = _to_item_response(existing_item, state)
        return JSONResponse(
            status_code=409,
            content={
                "message": "该文件已存在于知识库中，已为你关联到现有卡片。",
                "item_id": existing_item.id,
                "deduplicated": True,
                "item": response_item.model_dump(mode="json"),
            },
        )

    intent, mime_type = _validate_and_classify_upload(original_name, file.content_type)
    extracted_text = _extract_text_from_upload_bytes(content) if mime_type in SUPPORTED_TEXT_MIME_TYPES or mime_type in SUPPORTED_MARKDOWN_MIME_TYPES else ""

    with open(target_path, "wb") as output_file:
        output_file.write(content)

    public_path = _public_upload_path(relative_dir / target_name)
    resolved_title = (title or Path(original_name).stem or "未命名上传内容").strip()
    resolved_summary = (summary or "").strip()

    metadata_extra: Dict[str, Any] = {
        "original_filename": original_name,
        "mime_type": mime_type,
        "file_size": len(content),
        "has_long_summary": False,
        "processing_status": "queued",
    }
    if intent == "image":
        metadata_extra["cover_url"] = public_path
    if resolved_summary:
        metadata_extra["user_supplied_summary"] = resolved_summary

    item_payload = {
        "id": f"upload_{uuid.uuid4().hex}",
        "title": resolved_title,
        "source_type": "upload",
        "raw_link": public_path,
        "content_text": extracted_text or resolved_summary,
        "summary": resolved_summary or resolved_title,
        "intent": intent,
        "tags": [intent],
        "metadata_extra": metadata_extra,
        "file_hash": file_hash,
        "local_asset_path": str(target_path),
    }
    item_id = await _store_user_item(item_payload, current_user["id"], retention_days=retention_days)
    if auto_favorite:
        await _ensure_user_item_state(
            current_user["id"],
            item_id,
            is_favorited=True,
        )
    item, state = await _fetch_item_for_user(item_id, current_user["id"])

    if intent == "video":
        await _queue_video_summary_if_needed(item)
    elif intent == "image":
        await _queue_image_summary_if_needed(item)
    elif _is_pdf_item(item):
        await _queue_pdf_ocr_if_needed(item)
    elif _is_text_upload_mime(mime_type):
        await _queue_text_processing_if_needed(item)

    return _to_item_response(item, state)


@router.post("/parse", status_code=202)
async def parse_item_url(
    payload: ParseItemRequest = Body(...),
    current_user=Depends(get_current_user),
):
    plugin = await _resolve_plugin(payload.plugin_name)
    if not hasattr(plugin, "parse_single_item"):
        raise HTTPException(status_code=400, detail=f"插件 {payload.plugin_name} 不支持单条解析")

    try:
        from worker.plugins.pipeline import parse_single_plugin_item_task

        task = await parse_single_plugin_item_task.kiq(
            PLUGIN_NAME_ALIASES.get(payload.plugin_name, payload.plugin_name),
            payload.url,
            current_user["id"],
            payload.retention_days,
        )
    except Exception as exc:
        hub_log.exception("投递单条解析任务失败")
        raise HTTPException(status_code=500, detail=f"解析任务投递失败: {exc}")

    return {
        "status": "accepted",
        "task_id": str(task.task_id),
        "message": "链接解析任务已提交，Worker 正在后台抓取并入库，请稍候刷新信息流查看结果。",
    }


@router.post("/{item_id}/watch_later", response_model=ItemStateResponse)
async def toggle_item_watch_later(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            item = await session.get(ItemORM, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="找不到对应条目")

            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.user_id == current_user["id"],
                    UserItemStateORM.item_id == item_id,
                )
            )
            state = result.scalar_one_or_none()

            if state is None:
                raise HTTPException(status_code=404, detail="当前用户无权操作该条目")

            state.is_watch_later = not state.is_watch_later
            state.updated_at = now_in_app_timezone_naive()

    return ItemStateResponse(
        item_id=item_id,
        is_read=bool(state.is_read),
        is_watch_later=bool(state.is_watch_later),
        is_favorited=bool(state.is_favorited),
        vault_category_id=state.vault_category_id,
    )


@router.post("/{item_id}/favorite", response_model=ItemStateResponse)
async def toggle_item_favorite(item_id: str, current_user=Depends(get_current_user)):
    should_queue_download = False
    should_queue_video_summary = False
    should_queue_image_summary = False
    should_queue_pdf_ocr = False
    async with AsyncSessionLocal() as session:
        async with session.begin():
            item = await session.get(ItemORM, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="找不到对应条目")

            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.user_id == current_user["id"],
                    UserItemStateORM.item_id == item_id,
                )
            )
            state = result.scalar_one_or_none()

            if state is None:
                raise HTTPException(status_code=404, detail="当前用户无权操作该条目")

            was_favorited = bool(state.is_favorited)
            state.is_favorited = not state.is_favorited
            state.updated_at = now_in_app_timezone_naive()
            should_queue_download = (not was_favorited) and bool(state.is_favorited)
            should_queue_video_summary = should_queue_download and item.intent == "video"
            should_queue_image_summary = should_queue_download and item.intent == "image"
            should_queue_pdf_ocr = should_queue_download and _is_pdf_item(item) and bool(item.local_asset_path)

    if should_queue_download:
        await _queue_vault_download_if_needed(item_id, item, current_user["id"])
    if should_queue_video_summary:
        await _queue_video_summary_if_needed(item)
    if should_queue_image_summary:
        await _queue_image_summary_if_needed(item)
    if should_queue_pdf_ocr:
        await _queue_pdf_ocr_if_needed(item)

    return ItemStateResponse(
        item_id=item_id,
        is_read=bool(state.is_read),
        is_watch_later=bool(state.is_watch_later),
        is_favorited=bool(state.is_favorited),
        vault_category_id=state.vault_category_id,
    )


@router.post("/{item_id}/star", response_model=ItemStateResponse)
async def toggle_item_star(item_id: str, current_user=Depends(get_current_user)):
    return await toggle_item_watch_later(item_id, current_user)


@router.post("/read_batch")
async def mark_items_read_batch(payload: ReadBatchRequest, current_user=Depends(get_current_user)):
    item_ids = list(dict.fromkeys([item_id for item_id in payload.item_ids if item_id]))
    if not item_ids:
        return {"status": "success", "updated_count": 0}

    now = now_in_app_timezone_naive()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            valid_items_result = await session.execute(
                select(UserItemStateORM.item_id).where(
                    UserItemStateORM.user_id == current_user["id"],
                    UserItemStateORM.item_id.in_(item_ids),
                )
            )
            valid_item_ids = valid_items_result.scalars().all()
            if not valid_item_ids:
                return {"status": "success", "updated_count": 0}

            stmt = insert(UserItemStateORM).values(
                [
                    {
                        "user_id": current_user["id"],
                        "item_id": item_id,
                        "vault_category_id": None,
                        "is_read": True,
                        "is_watch_later": False,
                        "is_favorited": False,
                        "updated_at": now,
                    }
                    for item_id in valid_item_ids
                ]
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "item_id"],
                set_={
                    "is_read": True,
                    "updated_at": now,
                },
            )
            await session.execute(stmt)

    return {"status": "success", "updated_count": len(valid_item_ids)}


@router.delete("/{item_id}")
async def delete_item(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(delete(UserItemStateORM).where(UserItemStateORM.item_id == item_id))
            await session.execute(delete(ItemORM).where(ItemORM.id == item_id))
    return {"status": "success"}


@router.patch("/{item_id}/vault-category", response_model=ItemStateResponse)
async def assign_item_vault_category(
    item_id: str,
    payload: AssignVaultCategoryRequest = Body(...),
    current_user=Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.user_id == current_user["id"],
                    UserItemStateORM.item_id == item_id,
                )
            )
            state = result.scalar_one_or_none()
            if state is None:
                raise HTTPException(status_code=404, detail="当前用户无权操作该条目")

            if payload.vault_category_id:
                category = await session.get(VaultCategoryORM, payload.vault_category_id)
                if not category or category.user_id != current_user["id"]:
                    raise HTTPException(status_code=404, detail="目标分类不存在")
                state.vault_category_id = category.id
            else:
                state.vault_category_id = None

            state.updated_at = now_in_app_timezone_naive()

    return ItemStateResponse(
        item_id=item_id,
        is_read=bool(state.is_read),
        is_watch_later=bool(state.is_watch_later),
        is_favorited=bool(state.is_favorited),
        vault_category_id=state.vault_category_id,
    )


@router.post("/{item_id}/summarize")
async def summarize_item(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM)
            .join(UserItemStateORM, UserItemStateORM.item_id == ItemORM.id)
            .where(
                UserItemStateORM.user_id == current_user["id"],
                ItemORM.id == item_id,
            )
        )
        item = result.scalar_one_or_none()
        if not item:
            raise HTTPException(status_code=404, detail="当前用户无权访问该条目")

    import uuid as task_uuid
    task_id = str(task_uuid.uuid4())
    metadata = item.metadata_extra or {}

    if item.intent == "video":
        if metadata.get("has_long_summary") or metadata.get("raw_transcript"):
            return {
                "status": "skipped",
                "task_id": "",
                "message": "该视频已经完成过多媒体分析，无需重复生成。",
            }
        from worker.tasks import process_multimedia_task
        await process_multimedia_task.kiq(item_id, item.raw_link)
        msg = "AI 多媒体分析管线已启动，正在剥离音轨并生成胶卷快照，请稍后..."
    elif item.intent == "image":
        if metadata.get("has_long_summary") and metadata.get("image_understanding"):
            return {
                "status": "skipped",
                "task_id": "",
                "message": "该图片已经完成过图片理解，无需重复生成。",
            }
        from worker.tasks import process_image_understanding_task
        await process_image_understanding_task.kiq(item_id)
        msg = "图片理解任务已启动，正在提取视觉描述与图片文字，请稍后..."
    else:
        from worker.plugins.pipeline import summarize_repo_task
        await summarize_repo_task.kiq(item_id, task_id)
        msg = "AI 深度总结任务已启动，请稍后查询结果"

    return {
        "status": "accepted",
        "task_id": task_id,
        "message": msg,
    }


@router.get("/{item_id}/summary_status")
async def get_item_summary_status(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM)
            .join(UserItemStateORM, UserItemStateORM.item_id == ItemORM.id)
            .where(
                UserItemStateORM.user_id == current_user["id"],
                ItemORM.id == item_id,
            )
        )
        item = result.scalar_one_or_none()

    if not item:
        return {"item_id": item_id, "status": "not_found"}

    metadata = item.metadata_extra or {}
    has_long_summary = metadata.get("has_long_summary", False)

    if has_long_summary:
        return {
            "item_id": item_id,
            "status": "completed",
            "summary": metadata.get("long_summary") or item.summary,
        }

    return {
        "item_id": item_id,
        "status": "pending",
    }


from shared.schemas import HoverResponse


@router.get("/{item_id}/hover", response_model=HoverResponse)
async def get_item_hover_blocks(item_id: str, current_user=Depends(get_current_user)):
    """获取条目的 Server-Driven UI Hover 预览积木"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM)
            .join(UserItemStateORM, UserItemStateORM.item_id == ItemORM.id)
            .where(
                UserItemStateORM.user_id == current_user["id"],
                ItemORM.id == item_id,
            )
        )
        item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(status_code=404, detail="条目不存在或您无权访问")

    metadata_extra = item.metadata_extra or {}
    if "hover_blocks" in metadata_extra:
        return metadata_extra["hover_blocks"]

    plugin = None
    for candidate in plugin_manager.plugins.values():
        manifest = getattr(candidate, "_manifest", {}) or candidate.manifest or {}
        if manifest.get("source_type") == item.source_type:
            plugin = candidate
            break

    if not plugin:
        return []

    manifest = getattr(plugin, "_manifest", {}) or plugin.manifest or {}
    plugin_id = manifest.get("id")

    user_config_dict: Dict[str, Any] = {}
    for key in (manifest.get("settings_schema", {}) or {}).keys():
        value = await ConfigManager.get_config(
            plugin_id=plugin_id,
            key=key,
            user_id=current_user["id"],
        )
        if value is not None:
            user_config_dict[key] = value

    try:
        blocks = await plugin.get_hover_blocks(item_url=item.raw_link, user_config=user_config_dict)
        return blocks
    except Exception as exc:
        hub_log.exception("获取 Hover 信息失败")
        raise HTTPException(status_code=500, detail=f"获取 Hover 信息失败: {str(exc)}")
