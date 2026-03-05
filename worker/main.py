from worker.broker import broker  # 从纯净定义导入
from hub.core.logger import worker_log
import worker.ingestion.pipeline
import worker.plugins.github.task  # 导入 GitHub 任务模块

@broker.on_event("startup")
async def startup():
    worker_log.info("🚀 Iris-Worker 正在启动，准备接入神经中枢...")

@broker.on_event("shutdown")
async def shutdown():
    worker_log.info("🛑 Iris-Worker 正在安全关闭...")