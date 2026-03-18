import asyncio
from worker.broker import broker  # 从纯净定义导入
from shared.logger import worker_log
from shared.config import ConfigManager, ConfigKeys
import worker.ingestion.pipeline
import worker.plugins.pipeline  # 导入通用插件流水线模块

async def plugin_auto_sync_loop():
    worker_log.info("🕒 插件自动同步巡检协程已启动")
    while True:
        try:
            from shared.plugins.manager import plugin_manager
            manifests = plugin_manager.get_all_manifests()

            import datetime
            for manifest in manifests:
                plugin_id = manifest.get("id")
                if not plugin_id:
                    continue

                auto_sync = await ConfigManager.get_config(plugin_id, ConfigKeys.AUTO_SYNC)
                if auto_sync != "true":
                    continue

                last_sync = await ConfigManager.get_config(plugin_id, ConfigKeys.LAST_SYNC_TIME)
                interval_str = await ConfigManager.get_config(plugin_id, ConfigKeys.AUTO_SYNC_INTERVAL)
                interval_mins = int(interval_str) if interval_str else 60

                should_sync = False
                if not last_sync:
                    should_sync = True
                else:
                    try:
                        last_dt = datetime.datetime.fromisoformat(last_sync)
                        diff = datetime.datetime.now() - last_dt
                        if diff.total_seconds() >= interval_mins * 60:
                            should_sync = True
                    except Exception:
                        should_sync = True

                if should_sync:
                    worker_log.info(f"🔄 触发自动定时同步任务: {plugin_id}")
                    sync_limit = await ConfigManager.get_config(plugin_id, ConfigKeys.SYNC_LIMIT)
                    limit = int(sync_limit) if sync_limit else 100
                    await worker.plugins.pipeline.run_plugin_pipeline_task.kiq(plugin_id, limit=limit)
        except Exception as e:
            worker_log.error(f"❌ 插件自动同步巡检异常: {e}")
            
        # 巡检心跳：每 60 秒苏醒检查一次，能极其快速地响应用户修改配置
        await asyncio.sleep(60)

@broker.on_event("startup")
async def startup():
    worker_log.info("🚀 Iris-Worker 正在启动，准备接入神经中枢...")
    
    # 动态加载插件
    from shared.database import AsyncSessionLocal
    from shared.plugins.manager import plugin_manager
    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)
    
    asyncio.create_task(plugin_auto_sync_loop())

@broker.on_event("shutdown")
async def shutdown():
    worker_log.info("🛑 Iris-Worker 正在安全关闭...")
