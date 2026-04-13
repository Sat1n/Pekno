from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, select

from hub.api.schemas import LogTailResponse, MonitorMetricsResponse, PluginHealthResponse
from hub.core.billing import get_billing_config
from hub.core.security import require_admin
from shared.config import ConfigKeys, ConfigManager
from shared.database import AsyncSessionLocal
from shared.logger import get_log_file_path
from shared.models import ApiUsageORM, ItemORM, PluginRegistryORM
from shared.time_utils import now_in_app_timezone_naive

router = APIRouter(prefix="/api/admin", tags=["Monitor"])

ALLOWED_LOG_SERVICES = {"hub", "worker", "scheduler"}
MAX_LOG_LINES = 200


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


async def _get_plugin_health(plugin: PluginRegistryORM) -> PluginHealthResponse:
    plugin_id = plugin.plugin_id
    auto_sync = (await ConfigManager.get_config(plugin_id, ConfigKeys.AUTO_SYNC, "false")) == "true"
    interval_raw = await ConfigManager.get_config(plugin_id, ConfigKeys.AUTO_SYNC_INTERVAL, "60")
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

    return PluginHealthResponse(
        plugin_id=plugin_id,
        name=plugin.name,
        last_successful_sync_at=last_successful_sync_at,
        last_sync_at=last_sync_at,
        sync_status=sync_status or "idle",
        status=status,
        auto_sync=auto_sync,
        auto_sync_interval=auto_sync_interval,
        last_error=last_error or None,
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


@router.get("/metrics", response_model=MonitorMetricsResponse)
async def get_admin_metrics(current_user=Depends(require_admin)):
    now = now_in_app_timezone_naive()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with AsyncSessionLocal() as session:
        rag_backlog_result = await session.execute(
            select(func.count(ItemORM.id)).where(
                or_(ItemORM.summary.is_(None), ItemORM.summary == "", ItemORM.embedding.is_(None))
            )
        )
        rag_backlog_count = int(rag_backlog_result.scalar() or 0)

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
    abnormal_plugin_count = sum(1 for plugin in plugin_health if plugin.status != "Healthy")
    billing_config = await get_billing_config()

    return MonitorMetricsResponse(
        rag_backlog_count=rag_backlog_count,
        api_today_total_cost=api_today_total_cost,
        billing_currency=billing_config["currency"],
        abnormal_plugin_count=abnormal_plugin_count,
        plugins=plugin_health,
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
