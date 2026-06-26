from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, and_, desc
from shared.database import AsyncSessionLocal
from shared.models import SavedFilterORM, ItemORM, UserItemStateORM
from hub.core.security import get_current_user
import uuid

router = APIRouter(prefix="/api/saved-filters", tags=["saved-filters"])


class SavedFilterResponse(BaseModel):
    id: str
    name: str
    filter_params: dict
    sort_order: int
    last_content_at: Optional[str] = None
    created_at: str
    updated_at: str


class CreateSavedFilterRequest(BaseModel):
    name: str
    filter_params: dict


class UpdateSavedFilterRequest(BaseModel):
    name: Optional[str] = None
    filter_params: Optional[dict] = None
    sort_order: Optional[int] = None


def _to_response(filt: SavedFilterORM) -> SavedFilterResponse:
    return SavedFilterResponse(
        id=filt.id,
        name=filt.name,
        filter_params=filt.filter_params,
        sort_order=filt.sort_order,
        last_content_at=filt.last_content_at.isoformat() if filt.last_content_at else None,
        created_at=filt.created_at.isoformat(),
        updated_at=filt.updated_at.isoformat(),
    )


@router.get("", response_model=List[SavedFilterResponse])
async def get_saved_filters(current_user=Depends(get_current_user)):
    """获取用户保存的所有筛选条件（胶囊），按 last_content_at 降序排列"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SavedFilterORM)
            .where(SavedFilterORM.user_id == current_user["id"])
            .order_by(desc(SavedFilterORM.last_content_at), SavedFilterORM.sort_order)
        )
        filters = result.scalars().all()
        return [_to_response(f) for f in filters]


@router.post("", response_model=SavedFilterResponse)
async def create_saved_filter(
    request: CreateSavedFilterRequest,
    current_user=Depends(get_current_user),
):
    """创建新的筛选条件胶囊"""
    async with AsyncSessionLocal() as session:
        # 检查名称是否已存在
        existing = await session.execute(
            select(SavedFilterORM).where(
                and_(
                    SavedFilterORM.user_id == current_user["id"],
                    SavedFilterORM.name == request.name,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Filter with this name already exists")

        # 计算该筛选条件匹配的最新内容时间
        last_content_at = await _calculate_last_content_at(
            session, current_user["id"], request.filter_params
        )

        filt = SavedFilterORM(
            id=str(uuid.uuid4()),
            user_id=current_user["id"],
            name=request.name,
            filter_params=request.filter_params,
            last_content_at=last_content_at,
        )
        session.add(filt)
        await session.commit()
        await session.refresh(filt)
        return _to_response(filt)


@router.put("/{filter_id}", response_model=SavedFilterResponse)
async def update_saved_filter(
    filter_id: str,
    request: UpdateSavedFilterRequest,
    current_user=Depends(get_current_user),
):
    """更新筛选条件胶囊"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SavedFilterORM).where(
                and_(
                    SavedFilterORM.id == filter_id,
                    SavedFilterORM.user_id == current_user["id"],
                )
            )
        )
        filt = result.scalar_one_or_none()
        if not filt:
            raise HTTPException(status_code=404, detail="Filter not found")

        if request.name is not None:
            # 检查新名称是否冲突
            existing = await session.execute(
                select(SavedFilterORM).where(
                    and_(
                        SavedFilterORM.user_id == current_user["id"],
                        SavedFilterORM.name == request.name,
                        SavedFilterORM.id != filter_id,
                    )
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=400, detail="Filter with this name already exists")
            filt.name = request.name

        if request.filter_params is not None:
            filt.filter_params = request.filter_params
            # 重新计算最新内容时间
            filt.last_content_at = await _calculate_last_content_at(
                session, current_user["id"], request.filter_params
            )

        if request.sort_order is not None:
            filt.sort_order = request.sort_order

        await session.commit()
        await session.refresh(filt)
        return _to_response(filt)


@router.delete("/{filter_id}")
async def delete_saved_filter(
    filter_id: str,
    current_user=Depends(get_current_user),
):
    """删除筛选条件胶囊"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SavedFilterORM).where(
                and_(
                    SavedFilterORM.id == filter_id,
                    SavedFilterORM.user_id == current_user["id"],
                )
            )
        )
        filt = result.scalar_one_or_none()
        if not filt:
            raise HTTPException(status_code=404, detail="Filter not found")

        await session.delete(filt)
        await session.commit()
        return {"message": "Filter deleted"}


async def _calculate_last_content_at(session, user_id: str, filter_params: dict):
    """计算匹配筛选条件的最新内容时间"""
    stmt = (
        select(ItemORM.created_at)
        .join(
            UserItemStateORM,
            and_(
                UserItemStateORM.item_id == ItemORM.id,
                UserItemStateORM.user_id == user_id,
            ),
        )
        .order_by(desc(ItemORM.created_at))
        .limit(1)
    )

    # 应用筛选条件
    if filter_params.get("source_type"):
        stmt = stmt.where(ItemORM.source_type == filter_params["source_type"])
    if filter_params.get("author"):
        stmt = stmt.where(ItemORM.author.ilike(f"%{filter_params['author']}%"))
    if filter_params.get("intent"):
        stmt = stmt.where(ItemORM.intent == filter_params["intent"])
    if filter_params.get("vault_category_id"):
        stmt = stmt.where(UserItemStateORM.vault_category_id == filter_params["vault_category_id"])
    if filter_params.get("is_read") is not None:
        stmt = stmt.where(UserItemStateORM.is_read == filter_params["is_read"])
    if filter_params.get("favorited_only"):
        stmt = stmt.where(UserItemStateORM.is_favorited == True)

    result = await session.execute(stmt)
    row = result.first()
    return row[0] if row else None


async def refresh_capsule_last_content(user_id: str, item_created_at):
    """当新内容到达时，刷新匹配的胶囊的 last_content_at"""
    async with AsyncSessionLocal() as session:
        # 获取用户所有胶囊
        result = await session.execute(
            select(SavedFilterORM).where(SavedFilterORM.user_id == user_id)
        )
        filters = result.scalars().all()

        for filt in filters:
            # 简单检查：如果有任何筛选条件，暂时跳过复杂匹配
            # 实际应该检查新内容是否匹配胶囊的筛选条件
            if filt.last_content_at is None or item_created_at > filt.last_content_at:
                filt.last_content_at = item_created_at

        await session.commit()
