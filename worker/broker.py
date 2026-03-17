import os
import taskiq_redis
from taskiq import InMemoryBroker, TaskiqEvents, TaskiqState

from shared.logger import hub_log  # 请确认你的 shared logger 导入路径
from shared.plugins.manager import plugin_manager
from shared.database import AsyncSessionLocal 

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

# 根据环境选择 Broker
if os.getenv("USE_REDIS", "True") == "True":
    broker = taskiq_redis.ListQueueBroker(REDIS_URL)
else:
    broker = InMemoryBroker()

# ✨ 终极修复：监听 WORKER_STARTUP 事件，并传入 state ✨
@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def startup_event(state: TaskiqState):
    hub_log.info("🚀 Worker 进程苏醒，开始从记忆神殿读取插件...")
    
    # 开启一个数据库会话，传给 manager 让它去拉取名单
    async with AsyncSessionLocal() as session:
        await plugin_manager.load_enabled_plugins(session)
        
    hub_log.info("✅ Worker 插件装载完毕！")