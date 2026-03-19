from worker.broker import broker  # 从纯净定义导入
from shared.logger import worker_log
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduler import TaskiqScheduler
import worker.ingestion.pipeline
import worker.maintenance
import worker.plugins.pipeline  # 导入通用插件流水线模块

scheduler = TaskiqScheduler(broker, sources=[LabelScheduleSource(broker)])

@broker.on_event("startup")
async def startup():
    worker_log.info("🚀 Iris-Worker 正在启动，准备接入神经中枢...")
    
    # 动态加载插件
    from shared.database import AsyncSessionLocal
    from shared.plugins.manager import plugin_manager
    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)

@broker.on_event("shutdown")
async def shutdown():
    worker_log.info("🛑 Iris-Worker 正在安全关闭...")
