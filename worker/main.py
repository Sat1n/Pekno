import os
import sys

service_name = "scheduler" if "scheduler" in " ".join(sys.argv).lower() else "worker"
os.environ["IRIS_SERVICE"] = service_name

from shared.logger import configure_logging, detect_service_name, scheduler_log, worker_log
from taskiq.schedule_sources import LabelScheduleSource
from taskiq.scheduler.scheduler import TaskiqScheduler
from worker.broker import broker  # 从纯净定义导入
import worker.ingestion.pipeline
import worker.maintenance
import worker.plugins.pipeline  # 导入通用插件流水线模块

configure_logging()

scheduler = TaskiqScheduler(broker, sources=[LabelScheduleSource(broker)])

@broker.on_event("startup")
async def startup():
    if detect_service_name() == "scheduler":
        scheduler_log.info("⏰ Iris-Scheduler is ready and waiting for scheduled jobs.")
    else:
        worker_log.info("🚀 Iris-Worker is starting and connecting to the processing core...")
    
    # 动态加载插件
    from shared.database import AsyncSessionLocal
    from shared.plugins.manager import plugin_manager
    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)

@broker.on_event("shutdown")
async def shutdown():
    if detect_service_name() == "scheduler":
        scheduler_log.info("⏰ Iris-Scheduler is shutting down gracefully...")
    else:
        worker_log.info("🛑 Iris-Worker is shutting down gracefully...")
