from __future__ import annotations

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, select

from hub.api.schemas import AnnotationResponse
from hub.core.security import get_current_user
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserAnnotationsORM, UserItemStateORM
from shared.time_utils import now_in_app_timezone_naive

router = APIRouter(prefix="/api/items", tags=["Annotations"])


class AnnotationCreateRequest(BaseModel):
    content_raw: str = Field(min_length=1, max_length=20000)
    type: str = Field(default="general")
    anchor_data: dict = Field(default_factory=dict)


async def _ensure_item_visible(item_id: str, user_id: str) -> None:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM.id)
            .join(
                UserItemStateORM,
                and_(
                    UserItemStateORM.item_id == ItemORM.id,
                    UserItemStateORM.user_id == user_id,
                ),
            )
            .where(ItemORM.id == item_id)
        )
        visible_item_id = result.scalar_one_or_none()
    if not visible_item_id:
        raise HTTPException(status_code=404, detail="条目不存在或您无权访问")


@router.get("/{item_id}/annotations", response_model=list[AnnotationResponse])
async def get_item_annotations(item_id: str, current_user=Depends(get_current_user)):
    await _ensure_item_visible(item_id, current_user["id"])

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserAnnotationsORM)
            .where(
                UserAnnotationsORM.user_id == current_user["id"],
                UserAnnotationsORM.item_id == item_id,
            )
            .order_by(UserAnnotationsORM.created_at.desc())
        )
        annotations = result.scalars().all()

    return [
        AnnotationResponse(
            id=annotation.id,
            item_id=annotation.item_id,
            type=annotation.type,
            content_raw=annotation.content_raw,
            anchor_data=annotation.anchor_data or {},
            created_at=annotation.created_at,
        )
        for annotation in annotations
    ]


@router.post("/{item_id}/annotations", response_model=AnnotationResponse)
async def create_item_annotation(
    item_id: str,
    payload: AnnotationCreateRequest = Body(...),
    current_user=Depends(get_current_user),
):
    await _ensure_item_visible(item_id, current_user["id"])

    annotation = UserAnnotationsORM(
        id=str(uuid.uuid4()),
        user_id=current_user["id"],
        item_id=item_id,
        type=payload.type or "general",
        content_raw=payload.content_raw.strip(),
        anchor_data=payload.anchor_data or {},
        created_at=now_in_app_timezone_naive(),
    )

    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(annotation)

    return AnnotationResponse(
        id=annotation.id,
        item_id=annotation.item_id,
        type=annotation.type,
        content_raw=annotation.content_raw,
        anchor_data=annotation.anchor_data or {},
        created_at=annotation.created_at,
    )
