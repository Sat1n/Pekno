from sqlalchemy import select, text, or_
from hub.core.database import AsyncSessionLocal
from hub.core.database_models import ItemORM
from hub.core.llm.service import EmbeddingService

class SearchService:
    def __init__(self):
        self.embed_service = EmbeddingService()

    async def hybrid_search(self, query_text: str, limit: int = 10):
        # 1. 准备向量
        query_vector = await self.embed_service.get_vector(query_text)

        async with AsyncSessionLocal() as session:
            # 2. 构建混合查询语句
            # - cosine_distance 处理语义相似度
            # - ts_rank_cd 处理文本匹配相似度 (Postgres 内置全文检索)
            
            sql = text("""
                SELECT 
                    id, title, summary, tags,
                    (1 - (embedding <=> :vector)) as vector_score,
                    ts_rank_cd(
                        to_tsvector('chinese', title || ' ' || content_text || ' ' || summary), 
                        plainto_tsquery('chinese', :query)
                    ) as text_score
                FROM items
                ORDER BY (vector_score * 0.7 + text_score * 0.3) DESC
                LIMIT :limit
            """)
            
            # 注意：'chinese' 分词器需要你的 Postgres 安装了 zhparser，
            # 如果是默认环境，我们可以先用 'simple' 或者是直接在 Python 层做权重融合。
            
            # 为了兼容性，我们先用 SQLAlchemy 的逻辑实现一个基础版的融合：
            vector_stmt = (
                select(
                    ItemORM,
                    (1 - ItemORM.embedding.cosine_distance(query_vector)).label("v_score")
                )
                .where(or_(
                    ItemORM.title.icontains(query_text),
                    ItemORM.summary.icontains(query_text),
                    ItemORM.tags.any(query_text)
                )) # 这里加上基础关键词过滤
                .order_by(text("v_score DESC"))
                .limit(limit)
            )

            result = await session.execute(vector_stmt)
            return result.all()