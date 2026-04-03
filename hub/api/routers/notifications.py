from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, select

from hub.api.schemas import NotificationResponse
from hub.core.security import get_current_user
from shared.database import AsyncSessionLocal
from shared.models import UserNotificationORM
from shared.time_utils import now_in_app_timezone_naive

router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@router.get("", response_model=list[NotificationResponse])
async def get_notifications(
    limit: int = Query(30, ge=1, le=100),
    current_user=Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserNotificationORM)
            .where(UserNotificationORM.user_id == current_user["id"])
            .order_by(UserNotificationORM.created_at.desc())
            .limit(limit)
        )
        rows = result.scalars().all()
    return [NotificationResponse.model_validate(row, from_attributes=True) for row in rows]


@router.post("/{notification_id}/read", response_model=NotificationResponse)
async def mark_notification_read(notification_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserNotificationORM).where(
                UserNotificationORM.id == notification_id,
                UserNotificationORM.user_id == current_user["id"],
            )
        )
        notification = result.scalar_one_or_none()
        if not notification:
            raise HTTPException(status_code=404, detail="通知不存在")

        if notification.status != "read":
            notification.status = "read"
            notification.read_at = now_in_app_timezone_naive()
            await session.commit()
            await session.refresh(notification)

    return NotificationResponse.model_validate(notification, from_attributes=True)


@router.post("/read-all")
async def mark_all_notifications_read(current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserNotificationORM).where(
                UserNotificationORM.user_id == current_user["id"],
                UserNotificationORM.status != "read",
            )
        )
        notifications = result.scalars().all()
        now = now_in_app_timezone_naive()
        for notification in notifications:
            notification.status = "read"
            notification.read_at = now
        await session.commit()
    return {"status": "success"}


@router.delete("")
async def clear_notifications(current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        await session.execute(
            delete(UserNotificationORM).where(UserNotificationORM.user_id == current_user["id"])
        )
        await session.commit()
    return {"status": "success"}
