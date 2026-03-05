import asyncio
from worker.broker import broker  # 从纯净定义导入
from hub.core.logger import worker_log
from hub.core.config import ConfigManager, ConfigKeys
import worker.ingestion.pipeline
import worker.plugins.github.task  # 导入 GitHub 任务模块

async def github_auto_sync_loop():
    worker_log.info("🕒 GitHub 自动同步巡检协程已启动")
    while True:
        try:
            # 检查自动同步是否开启
            auto_sync = await ConfigManager.get_config(ConfigKeys.GITHUB_AUTO_SYNC)
            if auto_sync == "true":
                # 检查上一次同步时间
                last_sync = await ConfigManager.get_config(ConfigKeys.GITHUB_LAST_SYNC_TIME)
                interval_str = await ConfigManager.get_config(ConfigKeys.GITHUB_AUTO_SYNC_INTERVAL)
                interval_mins = int(interval_str) if interval_str else 60
                
                import datetime
                should_sync = False
                if not last_sync:
                    should_sync = True
                else:
                    try:
                        last_dt = datetime.datetime.fromisoformat(last_sync)
                        diff = datetime.datetime.now() - last_dt
                        if diff.total_seconds() >= interval_mins * 60:
                            should_sync = True
                    except:
                        should_sync = True
                        
                if should_sync:
                    worker_log.info("🔄 触发自动定时同步任务...")
                    sync_limit = await ConfigManager.get_config(ConfigKeys.GITHUB_SYNC_LIMIT)
                    limit = int(sync_limit) if sync_limit else 100
                    await worker.plugins.github.task.sync_github_stars_task.kiq(limit=limit)
        except Exception as e:
            worker_log.error(f"❌ GitHub 自动同步巡检异常: {e}")
            
        # 巡检心跳：每 60 秒苏醒检查一次，能极其快速地响应用户修改配置
        await asyncio.sleep(60)

@broker.on_event("startup")
async def startup():
    worker_log.info("🚀 Iris-Worker 正在启动，准备接入神经中枢...")
    asyncio.create_task(github_auto_sync_loop())

@broker.on_event("shutdown")
async def shutdown():
    worker_log.info("🛑 Iris-Worker 正在安全关闭...")