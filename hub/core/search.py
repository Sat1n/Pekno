import asyncio
from typing import List
from sqlalchemy import select, text, case, cast, Float
from shared.database import AsyncSessionLocal
from shared.models import ItemORM
from hub.core.llm.service import EmbeddingService
from shared.logger import hub_log

class SearchService:
    def __init__(self):
        self.embed_service = EmbeddingService()

    async def vector_search(self, query_text: str, limit: int = 5):
        """纯向量搜索"""
        query_vector = await self.embed_service.get_vector(query_text)
        async with AsyncSessionLocal() as session:
            # 使用 pgvector 的余弦距离
            stmt = (
                select(
                    ItemORM,
                    (1 - ItemORM.embedding.cosine_distance(query_vector)).label("score")
                )
                .order_by(text("score DESC"))
                .limit(limit)
            )
            result = await session.execute(stmt)
            return result.all()

    async def hybrid_search(self, query_text: str, limit: int = 5):
        """混合搜索 2.0：修复 label 报错，使用原生 case 表达式"""
        query_vector = await self.embed_service.get_vector(query_text)
        
        async with AsyncSessionLocal() as session:
            # 使用 SQLAlchemy 的 case 构造加分权重
            # 如果标题包含关键词，权重分给 0.5，摘要包含给 0.2
            search_pattern = f"%{query_text}%"
            
            t_score = case(
                (ItemORM.title.ilike(search_pattern), 0.5),
                (ItemORM.summary.ilike(search_pattern), 0.2),
                else_=0.0
            ).label("t_score")

            v_score = (1 - ItemORM.embedding.cosine_distance(query_vector)).label("v_score")

            stmt = (
                select(
                    ItemORM,
                    v_score,
                    t_score
                )
                .order_by((v_score + t_score).desc())
                .limit(limit)
            )
            
            result = await session.execute(stmt)
            return result.all()