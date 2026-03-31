import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from hub.api.schemas import VaultCategoryResponse
from hub.core.security import get_current_user
from shared.database import AsyncSessionLocal
from shared.models import UserItemStateORM, VaultCategoryORM
from shared.time_utils import now_in_app_timezone_naive

router = APIRouter(prefix="/api/vault", tags=["Vault"])

DEFAULT_CATEGORY_COLORS = [
    "#3B82F6",
    "#F97316",
    "#10B981",
    "#EF4444",
    "#8B5CF6",
    "#EAB308",
]


class VaultCategoryCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)
    color: str | None = Field(default=None, max_length=16)


class VaultCategoryUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=40)
    color: str | None = Field(default=None, max_length=16)


def _normalize_category_name(name: str) -> str:
    normalized = " ".join(name.strip().split())
    if not normalized:
        raise HTTPException(status_code=400, detail="分类名称不能为空")
    if normalized == "未分类":
        raise HTTPException(status_code=400, detail="“未分类”是系统保留名称")
    return normalized


def _to_category_response(category: VaultCategoryORM) -> VaultCategoryResponse:
    return VaultCategoryResponse(
        id=category.id,
        name=category.name,
        color=category.color,
        sort_order=category.sort_order,
        created_at=category.created_at,
    )


@router.get("/categories", response_model=list[VaultCategoryResponse])
async def get_vault_categories(current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(VaultCategoryORM)
            .where(VaultCategoryORM.user_id == current_user["id"])
            .order_by(VaultCategoryORM.sort_order.asc(), VaultCategoryORM.created_at.asc())
        )
        categories = result.scalars().all()
    return [_to_category_response(category) for category in categories]


@router.post("/categories", response_model=VaultCategoryResponse)
async def create_vault_category(payload: VaultCategoryCreateRequest, current_user=Depends(get_current_user)):
    category_name = _normalize_category_name(payload.name)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            existing = await session.execute(
                select(VaultCategoryORM.id).where(
                    VaultCategoryORM.user_id == current_user["id"],
                    func.lower(VaultCategoryORM.name) == category_name.lower(),
                )
            )
            if existing.scalar_one_or_none():
                raise HTTPException(status_code=409, detail="该分类名称已存在")

            order_result = await session.execute(
                select(func.max(VaultCategoryORM.sort_order)).where(VaultCategoryORM.user_id == current_user["id"])
            )
            max_sort_order = order_result.scalar_one_or_none()
            next_sort_order = (int(max_sort_order) + 1) if max_sort_order is not None else 0

            color = payload.color or DEFAULT_CATEGORY_COLORS[next_sort_order % len(DEFAULT_CATEGORY_COLORS)]
            category = VaultCategoryORM(
                id=str(uuid.uuid4()),
                user_id=current_user["id"],
                name=category_name,
                color=color,
                sort_order=next_sort_order,
                created_at=now_in_app_timezone_naive(),
                updated_at=now_in_app_timezone_naive(),
            )
            session.add(category)

    return _to_category_response(category)


@router.patch("/categories/{category_id}", response_model=VaultCategoryResponse)
async def update_vault_category(category_id: str, payload: VaultCategoryUpdateRequest, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            category = await session.get(VaultCategoryORM, category_id)
            if not category or category.user_id != current_user["id"]:
                raise HTTPException(status_code=404, detail="分类不存在")

            if payload.name is not None:
                category_name = _normalize_category_name(payload.name)
                existing = await session.execute(
                    select(VaultCategoryORM.id).where(
                        VaultCategoryORM.user_id == current_user["id"],
                        func.lower(VaultCategoryORM.name) == category_name.lower(),
                        VaultCategoryORM.id != category_id,
                    )
                )
                if existing.scalar_one_or_none():
                    raise HTTPException(status_code=409, detail="该分类名称已存在")
                category.name = category_name

            if payload.color is not None:
                category.color = payload.color

            category.updated_at = now_in_app_timezone_naive()

    return _to_category_response(category)


@router.delete("/categories/{category_id}")
async def delete_vault_category(category_id: str, current_user=Depends(get_current_user)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            category = await session.get(VaultCategoryORM, category_id)
            if not category or category.user_id != current_user["id"]:
                raise HTTPException(status_code=404, detail="分类不存在")

            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.user_id == current_user["id"],
                    UserItemStateORM.vault_category_id == category_id,
                )
            )
            states = result.scalars().all()
            for state in states:
                state.vault_category_id = None
                state.updated_at = now_in_app_timezone_naive()

            await session.delete(category)

    return {"status": "success"}
