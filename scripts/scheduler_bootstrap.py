import asyncio
import os

os.environ.setdefault("PEKNO_SERVICE", "scheduler")

from shared.logger import configure_logging, scheduler_log  # noqa: E402
from worker.maintenance import system_heartbeat_task, system_ttl_cleanup_task  # noqa: E402


async def main() -> None:
    configure_logging("scheduler")
    await system_heartbeat_task.kiq()
    await system_ttl_cleanup_task.kiq()
    scheduler_log.info("⏰ Startup bootstrap queued: initial heartbeat and TTL cleanup.")


if __name__ == "__main__":
    asyncio.run(main())
