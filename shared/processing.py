"""
AI 处理状态机的原子锁机制。

用于防止用户重复触发 AI 长总结任务, 并提供 Worker 崩溃后的超时恢复。
"""
from datetime import datetime, timedelta

from sqlalchemy import or_, and_, update

from shared.entities import AIProcessingStatus
from shared.models import ItemORM
from shared.time_utils import now_in_app_timezone_naive

TIMEOUT_MINUTES = 30


async def acquire_processing_lock(item_id: str, session) -> bool:
    """
    原子性地获取 AI 长总结处理锁。

    通过一条 UPDATE ... WHERE ... RETURNING 语句实现:
    - 如果 item 状态为 completed 或 pending_ai → 拿到锁, 写入 processing
    - 如果 item 状态为 processing 但 long_summary_at 超过 TIMEOUT_MINUTES → 认为旧锁过期, 重新拿锁 (崩溃恢复)
    - 否则 → 锁被持有, 返回 False

    返回 True 表示获取成功 (可以入队任务)。
    """
    now = now_in_app_timezone_naive()
    timeout_threshold = now - timedelta(minutes=TIMEOUT_MINUTES)

    result = await session.execute(
        update(ItemORM)
        .where(
            ItemORM.id == item_id,
            or_(
                ItemORM.ai_processing_status.in_([
                    AIProcessingStatus.completed,
                    AIProcessingStatus.pending_ai,
                ]),
                and_(
                    ItemORM.ai_processing_status == AIProcessingStatus.processing,
                    ItemORM.long_summary_at < timeout_threshold,
                ),
            ),
        )
        .values(
            ai_processing_status=AIProcessingStatus.processing,
            long_summary_at=now,
        )
        .returning(ItemORM.id)
    )
    return result.fetchone() is not None


async def release_processing_lock(item_id: str, session, *, success: bool) -> None:
    """
    释放处理锁。

    - success=True: 标记为 completed
    - success=False: 回退为 pending_ai (允许重试)
    """
    new_status = AIProcessingStatus.completed if success else AIProcessingStatus.pending_ai
    await session.execute(
        update(ItemORM)
        .where(ItemORM.id == item_id)
        .values(ai_processing_status=new_status)
    )
