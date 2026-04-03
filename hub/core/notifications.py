from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select

from shared.database import AsyncSessionLocal
from shared.models import UserItemStateORM, UserNotificationORM
from shared.time_utils import now_in_app_timezone_naive


async def _create_notifications(
    user_ids: Sequence[str],
    *,
    type: str,
    category: str,
    title: str,
    description: str,
    related_item_id: str | None = None,
    related_plugin_id: str | None = None,
) -> int:
    unique_user_ids = [user_id for user_id in dict.fromkeys(user_ids) if user_id]
    if not unique_user_ids:
        return 0

    created_at = now_in_app_timezone_naive()
    rows = [
        UserNotificationORM(
            user_id=user_id,
            type=type,
            category=category,
            title=title,
            description=description,
            status="unread",
            related_item_id=related_item_id,
            related_plugin_id=related_plugin_id,
            created_at=created_at,
        )
        for user_id in unique_user_ids
    ]

    async with AsyncSessionLocal() as session:
        session.add_all(rows)
        await session.commit()

    return len(rows)


async def create_notification_for_user(
    user_id: str | None,
    *,
    type: str,
    category: str,
    title: str,
    description: str,
    related_item_id: str | None = None,
    related_plugin_id: str | None = None,
) -> int:
    if not user_id:
        return 0
    return await _create_notifications(
        [user_id],
        type=type,
        category=category,
        title=title,
        description=description,
        related_item_id=related_item_id,
        related_plugin_id=related_plugin_id,
    )


async def create_notification_for_item_users(
    item_id: str,
    *,
    type: str,
    category: str,
    title: str,
    description: str,
    preferred_user_id: str | None = None,
) -> int:
    user_ids: list[str] = []
    if preferred_user_id:
        user_ids.append(preferred_user_id)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserItemStateORM.user_id).where(UserItemStateORM.item_id == item_id)
        )
        user_ids.extend(result.scalars().all())

    return await _create_notifications(
        user_ids,
        type=type,
        category=category,
        title=title,
        description=description,
        related_item_id=item_id,
    )
