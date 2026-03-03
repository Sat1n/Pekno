import os
import taskiq_redis
from taskiq import InMemoryBroker

REDIS_URL = os.getenv("REDIS_URL", "redis://127.0.0.1:6379")

# 根据环境选择 Broker
if os.getenv("USE_REDIS", "True") == "True":
    broker = taskiq_redis.ListQueueBroker(REDIS_URL)
else:
    broker = InMemoryBroker()