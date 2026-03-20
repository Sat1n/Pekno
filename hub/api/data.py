from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict, Any
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from sqlalchemy import select, func, delete
from pydantic import BaseModel
from hub.core.security import require_admin

router = APIRouter(prefix="/data", tags=["Data Management"])

class DataSourceStat(BaseModel):
    source_type: str
    count: int

@router.get("/sources", response_model=List[DataSourceStat])
async def get_data_sources(current_user=Depends(require_admin)):
    """获取所有数据源的统计信息"""
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM.source_type, func.count('*').label('count'))
            .group_by(ItemORM.source_type)
        )
        stats = result.all()
        return [DataSourceStat(source_type=row[0], count=row[1]) for row in stats]


@router.delete("/sources/{source_type}")
async def clear_data_source(source_type: str, current_user=Depends(require_admin)):
    """清除特定数据源的所有数据"""
    async with AsyncSessionLocal() as session:
        try:
            # 执行删除操作
            item_ids_result = await session.execute(
                select(ItemORM.id).where(ItemORM.source_type == source_type)
            )
            item_ids = item_ids_result.scalars().all()

            if item_ids:
                await session.execute(
                    delete(UserItemStateORM).where(UserItemStateORM.item_id.in_(item_ids))
                )

            result = await session.execute(
                delete(ItemORM).where(ItemORM.source_type == source_type)
            )
            await session.commit()
            
            return {
                "status": "success",
                "message": f"Successfully deleted data for source: {source_type}",
                "deleted_count": result.rowcount
            }
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=500, detail=str(e))
