from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, delete, select
from sqlalchemy.dialects.postgresql import insert

from hub.api.schemas import ItemResponse, ItemStateResponse, ReadBatchRequest
from hub.core.security import get_current_user
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from shared.time_utils import now_in_app_timezone_naive

router = APIRouter(prefix="/api/items", tags=["Items"])


def _to_item_response(item: ItemORM, state: Optional[UserItemStateORM]) -> ItemResponse:
    return ItemResponse(
        id=item.id,
        title=item.title,
        source_type=item.source_type,
        raw_link=item.raw_link,
        content_text=item.content_text,
        summary=item.summary,
        tags=item.tags or [],
        intent=item.intent,
        created_at=item.created_at,
        metadata_extra=item.metadata_extra or {},
        is_read=bool(state.is_read) if state else False,
        is_starred=bool(state.is_starred) if state else False,
    )


@router.get("", response_model=List[ItemResponse])
async def get_items(
    limit: Optional[int] = Query(default=None, ge=1),
    offset: int = Query(default=0, ge=0),
    starred_only: bool = Query(default=False),
    current_user=Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        stmt = (
            select(ItemORM, UserItemStateORM)
            .join(
                UserItemStateORM,
                and_(
                    UserItemStateORM.item_id == ItemORM.id,
                    UserItemStateORM.user_id == current_user["id"],
                ),
            )
            .order_by(ItemORM.created_at.desc())
            .offset(offset)
        )
        if starred_only:
            stmt = stmt.where(UserItemStateORM.is_starred == True)
        if limit is not None:
            stmt = stmt.limit(limit)

        result = await session.execute(stmt)
        rows = result.all()

    return [_to_item_response(item, state) for item, state in rows]


@router.post("/{item_id}/star", response_model=ItemStateResponse)
async def toggle_item_star(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            item = await session.get(ItemORM, item_id)
            if not item:
                raise HTTPException(status_code=404, detail="找不到对应条目")

            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.user_id == current_user["id"],
                    UserItemStateORM.item_id == item_id,
                )
            )
            state = result.scalar_one_or_none()

            if state is None:
                raise HTTPException(status_code=404, detail="当前用户无权操作该条目")

            state.is_starred = not state.is_starred
            state.updated_at = now_in_app_timezone_naive()

    return ItemStateResponse(
        item_id=item_id,
        is_read=bool(state.is_read),
        is_starred=bool(state.is_starred),
    )


@router.post("/read_batch")
async def mark_items_read_batch(payload: ReadBatchRequest, current_user=Depends(get_current_user)):
    item_ids = list(dict.fromkeys([item_id for item_id in payload.item_ids if item_id]))
    if not item_ids:
        return {"status": "success", "updated_count": 0}

    now = now_in_app_timezone_naive()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            valid_items_result = await session.execute(
                select(UserItemStateORM.item_id).where(
                    UserItemStateORM.user_id == current_user["id"],
                    UserItemStateORM.item_id.in_(item_ids),
                )
            )
            valid_item_ids = valid_items_result.scalars().all()
            if not valid_item_ids:
                return {"status": "success", "updated_count": 0}

            stmt = insert(UserItemStateORM).values(
                [
                    {
                        "user_id": current_user["id"],
                        "item_id": item_id,
                        "is_read": True,
                        "is_starred": False,
                        "updated_at": now,
                    }
                    for item_id in valid_item_ids
                ]
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["user_id", "item_id"],
                set_={
                    "is_read": True,
                    "updated_at": now,
                },
            )
            await session.execute(stmt)

    return {"status": "success", "updated_count": len(valid_item_ids)}


@router.delete("/{item_id}")
async def delete_item(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await session.execute(delete(UserItemStateORM).where(UserItemStateORM.item_id == item_id))
            await session.execute(delete(ItemORM).where(ItemORM.id == item_id))
    return {"status": "success"}


@router.post("/{item_id}/summarize")
async def summarize_item(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        link = await session.execute(
            select(UserItemStateORM).where(
                UserItemStateORM.user_id == current_user["id"],
                UserItemStateORM.item_id == item_id,
            )
        )
        if link.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="当前用户无权访问该条目")

    from worker.plugins.pipeline import summarize_repo_task
    import uuid

    task_id = str(uuid.uuid4())
    await summarize_repo_task.kiq(item_id, task_id)

    return {
        "status": "accepted",
        "task_id": task_id,
        "message": "AI 总结任务已启动，请稍后查询结果",
    }


@router.get("/{item_id}/summary_status")
async def get_item_summary_status(item_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM)
            .join(UserItemStateORM, UserItemStateORM.item_id == ItemORM.id)
            .where(
                UserItemStateORM.user_id == current_user["id"],
                ItemORM.id == item_id,
            )
        )
        item = result.scalar_one_or_none()

    if not item:
        return {"item_id": item_id, "status": "not_found"}

    metadata = item.metadata_extra or {}
    has_long_summary = metadata.get("has_long_summary", False)

    if has_long_summary:
        return {
            "item_id": item_id,
            "status": "completed",
            "summary": item.summary,
        }

    return {
        "item_id": item_id,
        "status": "pending",
    }
