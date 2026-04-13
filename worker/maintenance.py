from sqlalchemy import delete, select
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, PluginRegistryORM, UserItemStateORM
from datetime import datetime, timedelta
from worker.broker import broker
from shared.logger import worker_log
from shared.config import ConfigManager, ConfigKeys
from worker.plugins.pipeline import run_plugin_pipeline_task
from shared.time_utils import get_app_timezone, now_in_app_timezone_naive

@broker.task(
    task_name="system_heartbeat",
    schedule=[{"cron": "*/5 * * * *"}],
)
async def system_heartbeat_task():
    now = now_in_app_timezone_naive()
    next_update_at = now + timedelta(minutes=5)
    worker_log.info(
        f"💓 System heartbeat scan started. Next update at {next_update_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PluginRegistryORM.plugin_id).where(PluginRegistryORM.is_enabled == True)
        )
        plugin_ids = result.scalars().all()

    if not plugin_ids:
        worker_log.info("💓 Heartbeat scan finished. No enabled plugins were found.")
        return

    triggered_count = 0
    for plugin_id in plugin_ids:
        auto_sync = await ConfigManager.get_config(plugin_id, ConfigKeys.AUTO_SYNC, "false")
        if auto_sync != "true":
            continue

        sync_status = await ConfigManager.get_config(plugin_id, ConfigKeys.SYNC_STATUS, "idle")
        if sync_status == "running":
            worker_log.info(f"⏭️ [{plugin_id}] Heartbeat detected an active sync task. Skipping this auto-sync cycle.")
            continue

        interval_str = await ConfigManager.get_config(plugin_id, ConfigKeys.AUTO_SYNC_INTERVAL, "60")
        last_sync = await ConfigManager.get_config(plugin_id, ConfigKeys.LAST_SYNC_TIME)

        try:
            interval_mins = int(interval_str) if interval_str else 60
        except ValueError:
            interval_mins = 60

        should_sync = False
        next_sync_at = now
        if not last_sync:
            should_sync = True
        else:
            try:
                last_dt = datetime.fromisoformat(last_sync)
                next_sync_at = last_dt + timedelta(minutes=interval_mins)
                should_sync = (now - last_dt).total_seconds() >= interval_mins * 60
            except ValueError:
                should_sync = True

        if should_sync:
            worker_log.info(f"💓 [{plugin_id}] Auto-sync conditions met. Dispatching incremental sync task.")
            await run_plugin_pipeline_task.kiq(plugin_id)
            triggered_count += 1
        else:
            worker_log.info(
                f"💓 [{plugin_id}] Auto-sync interval has not elapsed yet. Next update at {next_sync_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )

    worker_log.info(
        f"💓 Heartbeat scan finished. Scanned {len(plugin_ids)} enabled plugins and triggered {triggered_count} auto-sync tasks."
    )

async def _delete_from_vector_store(expired_ids: list[str]) -> None:
    # Future hook: if we move embeddings into an external vector store
    # (Milvus / Qdrant / Chroma), delete those ids here as part of GC.
    #
    # Current architecture stores embeddings inline in Postgres via
    # ItemORM.embedding (pgvector), so deleting the row already releases
    # the vector payload and no extra action is needed.
    if expired_ids:
        worker_log.debug(
            f"🧠 [TTL Cleanup] Embeddings are stored inline in ItemORM via pgvector. No separate vector deletion is required for {len(expired_ids)} items."
        )


async def cleanup_expired_items() -> int:
    # Future config hook: heartbeat / TTL cleanup cron should eventually
    # be read from global admin settings stored in ConfigORM.
    now_local = now_in_app_timezone_naive()
    app_tz = get_app_timezone()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(ItemORM.id, ItemORM.created_at, ItemORM.retention_days).where(
                    ItemORM.retention_days > 0,
                    ItemORM.is_pinned == False
                )
            )
            rows = result.all()
            worker_log.debug(
                f"🧪 [TTL Cleanup] App timezone={app_tz.key}, current_time={now_local.isoformat(sep=' ', timespec='seconds')}, candidates={len(rows)}"
            )
            expired_ids = [
                row.id
                for row in rows
                if row.created_at + timedelta(hours=row.retention_days) < now_local
            ]

            if expired_ids:
                protected_result = await session.execute(
                    select(UserItemStateORM.item_id).where(
                        UserItemStateORM.item_id.in_(expired_ids),
                        (UserItemStateORM.is_favorited == True) | (UserItemStateORM.is_watch_later == True),
                    )
                )
                protected_ids = set(protected_result.scalars().all())
                if protected_ids:
                    worker_log.info(
                        f"🛡️ [TTL Cleanup] Found {len(protected_ids)} expired items that are still favorited or marked for later. Skipping physical deletion."
                    )
                    expired_ids = [item_id for item_id in expired_ids if item_id not in protected_ids]

            for row in rows[:10]:
                expires_at = row.created_at + timedelta(hours=row.retention_days)
                worker_log.debug(
                    f"🧪 [TTL Cleanup] item={row.id} created_at={row.created_at.isoformat(sep=' ', timespec='seconds')} "
                    f"retention_hours={row.retention_days} expires_at={expires_at.isoformat(sep=' ', timespec='seconds')} "
                    f"expired={expires_at < now_local}"
                )

            if not expired_ids:
                worker_log.info("🧹 [TTL Cleanup] Deleted 0 expired items.")
                return 0

            await _delete_from_vector_store(expired_ids)

            await session.execute(
                delete(UserItemStateORM).where(UserItemStateORM.item_id.in_(expired_ids))
            )
            delete_result = await session.execute(
                delete(ItemORM).where(ItemORM.id.in_(expired_ids))
            )

    deleted_count = delete_result.rowcount or len(expired_ids)
    worker_log.info(f"🧹 [TTL Cleanup] Deleted {deleted_count} expired items.")
    return deleted_count


@broker.task(
    task_name="system_ttl_cleanup",
    schedule=[{"cron": "*/5 * * * *"}],
)
async def system_ttl_cleanup_task():
    # Future config hook: this cron should be moved to global admin
    # settings once ConfigORM exposes platform-level scheduling options.
    next_cleanup_at = now_in_app_timezone_naive() + timedelta(minutes=5)
    worker_log.info(
        f"🧹 [TTL Cleanup] Scan started. Next update at {next_cleanup_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await cleanup_expired_items()
