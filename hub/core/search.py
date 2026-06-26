import asyncio
from typing import List, Optional, Tuple, Dict
from datetime import datetime
from sqlalchemy import select, text, case, cast, Float, and_, func, desc, or_
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from hub.core.llm.service import EmbeddingService
from shared.logger import hub_log

class SearchService:
    def __init__(self):
        self.embed_service = EmbeddingService()

    def _apply_filters(
        self,
        stmt,
        source_type: Optional[str] = None,
        favorited_only: bool = False,
        author: Optional[str] = None,
        intent: Optional[str] = None,
        vault_category_id: Optional[str] = None,
        is_read: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ):
        """通用筛选条件应用"""
        if source_type:
            stmt = stmt.where(ItemORM.source_type == source_type)
        if favorited_only:
            stmt = stmt.where(UserItemStateORM.is_favorited == True)
        if author:
            stmt = stmt.where(ItemORM.author.ilike(f"%{author}%"))
        if intent:
            stmt = stmt.where(ItemORM.intent == intent)
        if vault_category_id:
            stmt = stmt.where(UserItemStateORM.vault_category_id == vault_category_id)
        if is_read is not None:
            stmt = stmt.where(UserItemStateORM.is_read == is_read)
        if date_from:
            stmt = stmt.where(ItemORM.created_at >= date_from)
        if date_to:
            stmt = stmt.where(ItemORM.created_at <= date_to)
        return stmt

    async def _get_vector_candidates(
        self,
        query_text: str,
        user_id: str,
        limit: int = 60,
        source_type: Optional[str] = None,
        favorited_only: bool = False,
        author: Optional[str] = None,
        intent: Optional[str] = None,
        vault_category_id: Optional[str] = None,
        is_read: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[Tuple[ItemORM, float]]:
        """第一路召回：纯向量检索"""
        query_vector = await self.embed_service.get_vector(query_text)
        async with AsyncSessionLocal() as session:
            distance = ItemORM.embedding.cosine_distance(query_vector)
            stmt = (
                select(ItemORM, distance.label("distance"))
                .join(
                    UserItemStateORM,
                    and_(
                        UserItemStateORM.item_id == ItemORM.id,
                        UserItemStateORM.user_id == user_id,
                    ),
                )
                .where(ItemORM.embedding.is_not(None))
                .order_by(distance)
                .limit(limit)
            )
            stmt = self._apply_filters(
                stmt, source_type, favorited_only, author, intent,
                vault_category_id, is_read, date_from, date_to
            )
            result = await session.execute(stmt)
            return [(item, float(distance)) for item, distance in result.all()]

    async def _get_keyword_candidates(
        self,
        query_text: str,
        user_id: str,
        limit: int = 60,
        source_type: Optional[str] = None,
        favorited_only: bool = False,
        author: Optional[str] = None,
        intent: Optional[str] = None,
        vault_category_id: Optional[str] = None,
        is_read: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
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
            stmt = self._apply_filters(
                stmt, source_type, favorited_only, author, intent,
                vault_category_id, is_read, date_from, date_to
            )
            result = await session.execute(stmt)
            return result.scalars().all()

    async def hybrid_search(
        self,
        query_text: str,
        user_id: str,
        limit: int = 20,
        source_type: Optional[str] = None,
        favorited_only: bool = False,
        author: Optional[str] = None,
        intent: Optional[str] = None,
        vault_category_id: Optional[str] = None,
        is_read: Optional[bool] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> List[Tuple[ItemORM, float]]:
        """混合搜索 2.0：RRF 排序融合，返回值使用归一化相关性分数。"""
        vec_task = self._get_vector_candidates(
            query_text,
            user_id,
            limit=60,
            source_type=source_type,
            favorited_only=favorited_only,
            author=author,
            intent=intent,
            vault_category_id=vault_category_id,
            is_read=is_read,
            date_from=date_from,
            date_to=date_to,
        )
        kw_task = self._get_keyword_candidates(
            query_text,
            user_id,
            limit=60,
            source_type=source_type,
            favorited_only=favorited_only,
            author=author,
            intent=intent,
            vault_category_id=vault_category_id,
            is_read=is_read,
            date_from=date_from,
            date_to=date_to,
        )
        
        vec_items, kw_items = await asyncio.gather(vec_task, kw_task)
        
        k = 60
        rank_score_map: Dict[str, float] = {}
        relevance_score_map: Dict[str, float] = {}
        item_map: Dict[str, ItemORM] = {}
        
        # 1. 计算向量召回的 RRF 分数
        for rank, (item, distance) in enumerate(vec_items, start=1):
            if item.id not in rank_score_map:
                rank_score_map[item.id] = 0.0
                item_map[item.id] = item
            rank_score_map[item.id] += 1.0 / (k + rank)
            relevance_score_map[item.id] = max(
                relevance_score_map.get(item.id, 0.0),
                self._cosine_distance_to_relevance(distance),
            )
            
        # 2. 计算关键词召回的 RRF 分数
        for rank, item in enumerate(kw_items, start=1):
            if item.id not in rank_score_map:
                rank_score_map[item.id] = 0.0
                item_map[item.id] = item
            rank_score_map[item.id] += 1.0 / (k + rank)
            relevance_score_map[item.id] = max(
                relevance_score_map.get(item.id, 0.0),
                self._keyword_rank_to_relevance(rank),
            )
            
        # 3. 按合并后的 RRF 分数倒序排列
        sorted_results = sorted(
            rank_score_map.items(), key=lambda x: x[1], reverse=True
        )[:limit]
        
        return [(item_map[item_id], relevance_score_map.get(item_id, 0.0)) for item_id, _ in sorted_results]

    @staticmethod
    def _cosine_distance_to_relevance(distance: float) -> float:
        """Map pgvector cosine distance to a 0..1 relevance score.

        pgvector cosine distance is smaller for better matches. For normalized
        embeddings it is commonly in the 0..2 range; values above 1 represent
        weak or opposite matches and should not surface as negative percentages.
        """
        return max(0.0, min(1.0, 1.0 - distance))

    @staticmethod
    def _keyword_rank_to_relevance(rank: int) -> float:
        """Fallback score for keyword-only hits when no vector match exists."""
        return max(0.0, min(1.0, 1.0 - ((rank - 1) * 0.03)))
