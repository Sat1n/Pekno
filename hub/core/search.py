import asyncio
from typing import List, Optional, Tuple, Dict
from sqlalchemy import select, text, case, cast, Float, and_, func, desc, or_
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from hub.core.llm.service import EmbeddingService
from shared.logger import hub_log

class SearchService:
    def __init__(self):
        self.embed_service = EmbeddingService()

    async def _get_vector_candidates(
        self, query_text: str, user_id: str, limit: int = 60, source_type: Optional[str] = None
    ) -> List[ItemORM]:
        """第一路召回：纯向量检索"""
        query_vector = await self.embed_service.get_vector(query_text)
        async with AsyncSessionLocal() as session:
            stmt = (
                select(ItemORM)
                .join(
                    UserItemStateORM,
                    and_(
                        UserItemStateORM.item_id == ItemORM.id,
                        UserItemStateORM.user_id == user_id,
                    ),
                )
                .order_by(ItemORM.embedding.cosine_distance(query_vector))
                .limit(limit)
            )
            if source_type:
                stmt = stmt.where(ItemORM.source_type == source_type)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def _get_keyword_candidates(
        self, query_text: str, user_id: str, limit: int = 60, source_type: Optional[str] = None
    ) -> List[ItemORM]:
        """第二路召回：全文检索"""
        async with AsyncSessionLocal() as session:
            tsquery = func.plainto_tsquery('simple', query_text)
            tsvector = func.to_tsvector('simple', ItemORM.title)
            
            match_cond = or_(
                ItemORM.title.op('@@')(tsquery),
                ItemORM.title.ilike(f"%{query_text}%")
            )
            
            stmt = (
                select(ItemORM)
                .join(
                    UserItemStateORM,
                    and_(
                        UserItemStateORM.item_id == ItemORM.id,
                        UserItemStateORM.user_id == user_id,
                    ),
                )
                .where(match_cond)
                .order_by(desc(func.ts_rank(tsvector, tsquery)))
                .limit(limit)
            )
            if source_type:
                stmt = stmt.where(ItemORM.source_type == source_type)
            result = await session.execute(stmt)
            return result.scalars().all()

    async def hybrid_search(
        self, query_text: str, user_id: str, limit: int = 20, source_type: Optional[str] = None
    ) -> List[Tuple[ItemORM, float]]:
        """混合搜索 2.0：RRF 算法融合"""
        vec_task = self._get_vector_candidates(query_text, user_id, limit=60, source_type=source_type)
        kw_task = self._get_keyword_candidates(query_text, user_id, limit=60, source_type=source_type)
        
        vec_items, kw_items = await asyncio.gather(vec_task, kw_task)
        
        k = 60
        score_map: Dict[str, float] = {}
        item_map: Dict[str, ItemORM] = {}
        
        # 1. 计算向量召回的 RRF 分数
        for rank, item in enumerate(vec_items, start=1):
            if item.id not in score_map:
                score_map[item.id] = 0.0
                item_map[item.id] = item
            score_map[item.id] += 1.0 / (k + rank)
            
        # 2. 计算关键词召回的 RRF 分数
        for rank, item in enumerate(kw_items, start=1):
            if item.id not in score_map:
                score_map[item.id] = 0.0
                item_map[item.id] = item
            score_map[item.id] += 1.0 / (k + rank)
            
        # 3. 按合并后的 RRF 分数倒序排列
        sorted_results = sorted(
            score_map.items(), key=lambda x: x[1], reverse=True
        )[:limit]
        
        return [(item_map[item_id], score) for item_id, score in sorted_results]
