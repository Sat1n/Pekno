from sqlalchemy import delete, select
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, PluginRegistryORM
from datetime import datetime, timedelta
from worker.broker import broker
from shared.logger import worker_log
from shared.config import ConfigManager, ConfigKeys
from worker.plugins.pipeline import run_plugin_pipeline_task

@broker.task(
    task_name="system_heartbeat",
    schedule=[{"cron": "*/5 * * * *"}],
)
async def system_heartbeat_task():
    now = datetime.now()
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

async def cleanup_expired_items():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(ItemORM.id, ItemORM.created_at, ItemORM.retention_days).where(
                    ItemORM.retention_days > 0,
                    ItemORM.is_pinned == False
                )
            )
            rows = result.all()
            expired_ids = [
                row.id
                for row in rows
                if row.created_at < datetime.now() - timedelta(hours=row.retention_days)
            ]

            if not expired_ids:
                print("🧹 自动清理完成，未发现过期数据。")
                return

            delete_result = await session.execute(
                delete(ItemORM).where(ItemORM.id.in_(expired_ids))
            )
            print(f"🧹 自动清理完成，移除了 {delete_result.rowcount} 条过期数据。")
