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
        f"💓 系统心跳巡检开始，next update at {next_update_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(PluginRegistryORM.plugin_id).where(PluginRegistryORM.is_enabled == True)
        )
        plugin_ids = result.scalars().all()

    if not plugin_ids:
        worker_log.info("💓 心跳巡检完成：没有启用中的插件。")
        return

    triggered_count = 0
    for plugin_id in plugin_ids:
        auto_sync = await ConfigManager.get_config(plugin_id, ConfigKeys.AUTO_SYNC, "false")
        if auto_sync != "true":
            continue

        sync_status = await ConfigManager.get_config(plugin_id, ConfigKeys.SYNC_STATUS, "idle")
        if sync_status == "running":
            worker_log.info(f"⏭️ [{plugin_id}] 心跳检测到任务正在运行，跳过本轮自动同步。")
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
            worker_log.info(f"💓 [{plugin_id}] 满足自动同步条件，发送增量同步指令。")
            await run_plugin_pipeline_task.kiq(plugin_id)
            triggered_count += 1
        else:
            worker_log.info(
                f"💓 [{plugin_id}] 自动同步未到时间，next update at {next_sync_at.strftime('%Y-%m-%d %H:%M:%S')}"
            )

    worker_log.info(
        f"💓 心跳巡检完成：扫描 {len(plugin_ids)} 个启用插件，触发 {triggered_count} 个自动同步。"
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
            f"🧠 [TTL 清理] pgvector 内嵌于 ItemORM，无需额外删除向量索引，共 {len(expired_ids)} 条。"
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
                f"🧪 [TTL 清理] 当前应用时区={app_tz.key}，当前时间={now_local.isoformat(sep=' ', timespec='seconds')}，候选数据={len(rows)}"
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
                        f"🛡️ [TTL 清理] 检测到 {len(protected_ids)} 条已被收藏或加入稍后再看的过期数据，跳过物理销毁。"
                    )
                    expired_ids = [item_id for item_id in expired_ids if item_id not in protected_ids]

            for row in rows[:10]:
                expires_at = row.created_at + timedelta(hours=row.retention_days)
                worker_log.debug(
                    f"🧪 [TTL 清理] item={row.id} created_at={row.created_at.isoformat(sep=' ', timespec='seconds')} "
                    f"retention_hours={row.retention_days} expires_at={expires_at.isoformat(sep=' ', timespec='seconds')} "
                    f"expired={expires_at < now_local}"
                )

            if not expired_ids:
                worker_log.info("🧹 [TTL 清理] 成功销毁了 0 条过期数据。")
                return 0

            await _delete_from_vector_store(expired_ids)

            await session.execute(
                delete(UserItemStateORM).where(UserItemStateORM.item_id.in_(expired_ids))
            )
            delete_result = await session.execute(
                delete(ItemORM).where(ItemORM.id.in_(expired_ids))
            )

    deleted_count = delete_result.rowcount or len(expired_ids)
    worker_log.info(f"🧹 [TTL 清理] 成功销毁了 {deleted_count} 条过期数据。")
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
        f"🧹 [TTL 清理] 开始巡检，next update at {next_cleanup_at.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    await cleanup_expired_items()
