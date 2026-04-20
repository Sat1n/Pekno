import os
import taskiq_redis
from taskiq import InMemoryBroker, TaskiqEvents, TaskiqState

from shared.logger import configure_logging, worker_log
from shared.plugins.manager import plugin_manager
from shared.database import AsyncSessionLocal 

os.environ.setdefault("PEKNO_SERVICE", "worker")
configure_logging()

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

# 根据环境选择 Broker
if os.getenv("USE_REDIS", "True") == "True":
    broker = taskiq_redis.ListQueueBroker(REDIS_URL)
else:
    broker = InMemoryBroker()

# ✨ 终极修复：监听 WORKER_STARTUP 事件，并传入 state ✨
@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup_event(state: TaskiqState):
    worker_log.info("🚀 Worker process is online. Loading enabled plugins...")
    
    # 开启一个数据库会话，传给 manager 让它去拉取名单
    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)
        
    worker_log.info("✅ Worker plugin registry loaded successfully.")

# 必须在这里导入具体的 tasks 模块，否则 TaskIQ 无法在启动时发现并注册这些任务
import worker.tasks
import worker.plugins.pipeline
