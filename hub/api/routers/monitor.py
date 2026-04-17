from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select

from hub.api.schemas import (
    ForceProcessResponse,
    LogTailResponse,
    MonitorMetricsResponse,
    PluginHealthResponse,
    UsageTrendPointResponse,
    UsageTrendResponse,
)
from hub.core.billing import get_billing_state
from hub.core.security import require_admin
from shared.config import ConfigKeys, ConfigManager
from shared.database import AsyncSessionLocal
from shared.logger import get_log_file_path
from shared.models import ApiUsageORM, ItemORM, PluginRegistryORM
from shared.plugins.manager import plugin_manager
from shared.time_utils import now_in_app_timezone_naive

router = APIRouter(prefix="/api/admin", tags=["Monitor"])

ALLOWED_LOG_SERVICES = {"hub", "worker", "scheduler"}
MAX_LOG_LINES = 200
WARNING_THRESHOLD_RATIO = 0.9


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_pdf_item(item: ItemORM) -> bool:
    metadata = item.metadata_extra or {}
    mime_type = str(metadata.get("mime_type") or metadata.get("vault_download_content_type") or "").lower()
    candidate = str(item.local_asset_path or item.raw_link or "").lower()
    return mime_type == "application/pdf" or candidate.endswith(".pdf")


def _is_text_upload_item(item: ItemORM) -> bool:
    metadata = item.metadata_extra or {}
    mime_type = str(metadata.get("mime_type") or "").lower()
    return mime_type in {
        "text/plain",
        "text/markdown",
        "text/x-markdown",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }


def _is_retryable_failure(item: ItemORM) -> bool:
    metadata = item.metadata_extra or {}
    status = str(metadata.get("processing_status") or "").lower()
    return status in {"failed", "queued", "pending", "processing"}


def _needs_rag_processing(item: ItemORM) -> bool:
    metadata = item.metadata_extra or {}
    if _is_retryable_failure(item):
        return True
    if item.embedding is None:
        return True
    if not (item.summary or "").strip():
        return True
    if item.intent == "image" and not metadata.get("image_understanding"):
        return True
    if _is_pdf_item(item):
        ocr_meta = metadata.get("ocr") if isinstance(metadata.get("ocr"), dict) else {}
        return ocr_meta.get("status") not in {"completed", "disabled"}
    return False


def _build_billing_warning(state: dict) -> bool:
    limit_value = float(state.get("api_limit_value") or 0)
    if limit_value <= 0:
        return False
    limit_type = state.get("api_limit_type")
    used_value = state.get("used_tokens", 0) if limit_type == "token" else state.get("used_cost", 0.0)
    return float(used_value) >= limit_value * WARNING_THRESHOLD_RATIO


async def _get_plugin_setting(plugin: PluginRegistryORM, key: str, fallback: str) -> str:
    value = await ConfigManager.get_config(plugin.plugin_id, key)
    if value not in (None, ""):
        return value

    plugin_instance = plugin_manager.get_plugin(plugin.plugin_id)
    schema = (plugin_instance.manifest.get("settings_schema") or {}).get(key) if plugin_instance else None
    default = schema.get("default") if schema else None
    if default in (None, ""):
        return fallback
    return str(default).lower() if isinstance(default, bool) else str(default)


async def _get_plugin_health(plugin: PluginRegistryORM) -> PluginHealthResponse:
    plugin_id = plugin.plugin_id
    auto_sync = (await _get_plugin_setting(plugin, ConfigKeys.AUTO_SYNC, "false")) == "true"
    interval_raw = await _get_plugin_setting(plugin, ConfigKeys.AUTO_SYNC_INTERVAL, "60")
    sync_status = await ConfigManager.get_config(plugin_id, ConfigKeys.SYNC_STATUS, "idle")
    last_sync_at = _parse_dt(await ConfigManager.get_config(plugin_id, ConfigKeys.LAST_SYNC_TIME))
    last_successful_sync_at = _parse_dt(
        await ConfigManager.get_config(plugin_id, ConfigKeys.LAST_SUCCESSFUL_SYNC_TIME)
    )
    last_sync_result = await ConfigManager.get_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "idle")
    last_error = await ConfigManager.get_config(plugin_id, ConfigKeys.LAST_SYNC_ERROR, "")

    try:
        auto_sync_interval = max(1, int(interval_raw or "60"))
    except ValueError:
        auto_sync_interval = 60

    now = now_in_app_timezone_naive()
    stale_threshold = timedelta(minutes=auto_sync_interval * 2)

    if sync_status == "running":
        status = "Healthy"
    elif last_sync_result == "error":
        status = "Error"
    elif auto_sync and (
        last_successful_sync_at is None or now - last_successful_sync_at > stale_threshold
    ):
        status = "Stale"
    elif auto_sync and last_sync_at is None:
        status = "Stale"
    else:
        status = "Healthy"

    visible_error = last_error if last_sync_result in {"error", "warning"} and last_error else None

    return PluginHealthResponse(
        plugin_id=plugin_id,
        name=plugin.name,
        last_successful_sync_at=last_successful_sync_at,
        last_sync_at=last_sync_at,
        sync_status=sync_status or "idle",
        status=status,
        auto_sync=auto_sync,
        auto_sync_interval=auto_sync_interval,
        last_error=visible_error,
    )


def _read_log_tail(path: Path, max_lines: int = MAX_LOG_LINES) -> str:
    if not path.exists():
        return ""

    chunk_size = 4096
    with path.open("rb") as handle:
        handle.seek(0, 2)
        file_size = handle.tell()
        buffer = bytearray()
        position = file_size
        line_count = 0

        while position > 0 and line_count <= max_lines:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            chunk = handle.read(read_size)
            buffer = chunk + buffer
            line_count = buffer.count(b"\n")

        text = buffer.decode("utf-8", errors="replace")
        return "\n".join(text.splitlines()[-max_lines:])


async def _get_monitor_items() -> tuple[int, float, list[PluginHealthResponse], dict]:
    now = now_in_app_timezone_naive()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as session:
        backlog_result = await session.execute(select(ItemORM))
        backlog_items = backlog_result.scalars().all()
        rag_backlog_count = sum(1 for item in backlog_items if _needs_rag_processing(item))

        api_today_result = await session.execute(
            select(func.coalesce(func.sum(ApiUsageORM.estimated_cost), 0.0)).where(
                ApiUsageORM.created_at >= day_start
            )
        )
        api_today_total_cost = float(api_today_result.scalar() or 0.0)

        plugins_result = await session.execute(
            select(PluginRegistryORM)
            .where(PluginRegistryORM.is_enabled == True)
            .order_by(PluginRegistryORM.name.asc())
        )
        plugins = plugins_result.scalars().all()

    plugin_health = [await _get_plugin_health(plugin) for plugin in plugins]
    billing_state = await get_billing_state()
    return rag_backlog_count, api_today_total_cost, plugin_health, billing_state


@router.get("/metrics", response_model=MonitorMetricsResponse)
async def get_admin_metrics(current_user=Depends(require_admin)):
    rag_backlog_count, api_today_total_cost, plugin_health, billing_state = await _get_monitor_items()
    abnormal_plugin_count = sum(1 for plugin in plugin_health if plugin.status != "Healthy")

    return MonitorMetricsResponse(
        rag_backlog_count=rag_backlog_count,
        api_today_total_cost=api_today_total_cost,
        api_limit_type=billing_state["api_limit_type"],
        api_limit_value=float(billing_state["api_limit_value"]),
        used_tokens=int(billing_state["used_tokens"]),
        used_cost=float(billing_state["used_cost"]),
        limit_exceeded=bool(billing_state["limit_exceeded"]),
        billing_warning=_build_billing_warning(billing_state),
        warning_threshold_ratio=WARNING_THRESHOLD_RATIO,
        billing_currency=billing_state["currency"],
        abnormal_plugin_count=abnormal_plugin_count,
        plugins=plugin_health,
    )


@router.get("/metrics/usage-trend", response_model=UsageTrendResponse)
async def get_usage_trend(current_user=Depends(require_admin)):
    today = now_in_app_timezone_naive().date()
    start_day = today - timedelta(days=6)
    start_dt = datetime.combine(start_day, datetime.min.time())

    async with AsyncSessionLocal() as session:
        rows = await session.execute(
            select(
                func.date(ApiUsageORM.created_at),
                func.coalesce(func.sum(ApiUsageORM.total_tokens), 0),
                func.coalesce(func.sum(ApiUsageORM.estimated_cost), 0.0),
            )
            .where(ApiUsageORM.created_at >= start_dt)
            .group_by(func.date(ApiUsageORM.created_at))
            .order_by(func.date(ApiUsageORM.created_at).asc())
        )
        usage_rows = rows.all()

    usage_by_day: dict[date, tuple[int, float]] = {
        row_date: (int(total_tokens or 0), float(total_cost or 0.0))
        for row_date, total_tokens, total_cost in usage_rows
        if row_date
    }

    points: list[UsageTrendPointResponse] = []
    for offset in range(7):
        current_day = start_day + timedelta(days=offset)
        tokens, cost = usage_by_day.get(current_day, (0, 0.0))
        points.append(
            UsageTrendPointResponse(
                date=current_day.isoformat(),
                total_tokens=tokens,
                total_cost=cost,
            )
        )

    billing_state = await get_billing_state()
    return UsageTrendResponse(
        api_limit_type=billing_state["api_limit_type"],
        api_limit_value=float(billing_state["api_limit_value"]),
        currency=billing_state["currency"],
        used_tokens=int(billing_state["used_tokens"]),
        used_cost=float(billing_state["used_cost"]),
        limit_exceeded=bool(billing_state["limit_exceeded"]),
        billing_warning=_build_billing_warning(billing_state),
        warning_threshold_ratio=WARNING_THRESHOLD_RATIO,
        points=points,
    )


@router.post("/queue/force-process", response_model=ForceProcessResponse)
async def force_process_queue(current_user=Depends(require_admin)):
    from shared.entities import UniversalItem
    from worker.ingestion.pipeline import process_new_item_task
    from worker.tasks import (
        process_image_understanding_task,
        process_multimedia_task,
        process_pdf_ocr_task,
        process_uploaded_text_document_task,
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ItemORM).order_by(ItemORM.created_at.desc()))
        items = result.scalars().all()

    requeued_count = 0

    for item in items:
        if not _needs_rag_processing(item):
            continue

        if item.intent == "image":
            await process_image_understanding_task.kiq(item.id, None)
            requeued_count += 1
            continue

        if item.intent in {"video", "audio"}:
            await process_multimedia_task.kiq(item.id, item.raw_link, None)
            requeued_count += 1
            continue

        if _is_pdf_item(item):
            await process_pdf_ocr_task.kiq(item.id, None)
            requeued_count += 1
            continue

        if _is_text_upload_item(item):
            await process_uploaded_text_document_task.kiq(item.id, None)
            requeued_count += 1
            continue

        universal_item = UniversalItem(
            id=item.id,
            title=item.title,
            source_type=item.source_type,
            raw_link=item.raw_link,
            intent=item.intent,
            retention_hours=item.retention_days,
            capabilities=["summarize"] if (item.content_text or item.summary) else [],
            content_text=item.content_text,
            summary=item.summary,
            tags=item.tags or [],
            metadata_extra=item.metadata_extra or {},
            auto_short_summary=True,
            source_user_id=None,
        )
        await process_new_item_task.kiq(universal_item.model_dump(mode="json"))
        requeued_count += 1

    return ForceProcessResponse(
        status="accepted",
        requeued_count=requeued_count,
        message=f"已重新投递 {requeued_count} 条待处理内容。",
    )


@router.get("/logs/{service}", response_model=LogTailResponse)
async def get_admin_logs(service: str, current_user=Depends(require_admin)):
    normalized = service.strip().lower()
    if normalized not in ALLOWED_LOG_SERVICES:
        raise HTTPException(status_code=400, detail="service 必须为 hub、worker 或 scheduler")

    content = _read_log_tail(get_log_file_path(normalized))
    return LogTailResponse(
        service=normalized,  # type: ignore[arg-type]
        content=content,
        lines=len(content.splitlines()) if content else 0,
    )
