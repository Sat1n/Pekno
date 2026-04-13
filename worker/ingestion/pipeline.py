from shared.entities import UniversalItem
from shared.logger import worker_log
from worker.broker import broker
from shared.database import AsyncSessionLocal  # 导入会话工厂
from shared.models import ItemORM, UserItemStateORM     # 导入数据库模型
from sqlalchemy.dialects.postgresql import insert
from hub.core.billing import QuotaExceededException
from hub.core.llm.service import LLMManager

class IngestionPipeline:
    def __init__(self):
        self.logger = worker_log
        self.ai = LLMManager()
        

    async def process_item(self, item: UniversalItem):
        self.logger.info(f">>> 接收到新任务: {item.title} (ID: {item.id})")

        # DEBUG 记录插件私有数据，防止 metadata_extra 丢失字段
        self.logger.debug(f"DEBUG - [Entry] 插件私有元数据: {item.metadata_extra}")

        try:
            core_text = self._build_core_text(item)

            if item.auto_short_summary and item.capabilities and "summarize" in item.capabilities:
                item.summary = await self._generate_summary(core_text)
            else:
                item.summary = item.content_text or item.title
                self.logger.info(f"⏭️ 跳过 AI 短总结: {item.title} (source={item.source_type}, auto_short_summary={item.auto_short_summary})")

            item.tags = await self._auto_tagging(core_text)

            # 3. 核心：执行数据库持久化
            await self._store_to_vector_db(item, core_text)
            
            self.logger.info(f"✅ 成功同步至 Postgres: {item.id}")
            return item
        except Exception as e:
            self.logger.error(f"❌ 入库失败 {item.id}: {str(e)}", exc_info=True)
            raise e
    
    def _build_core_text(self, item: UniversalItem) -> str:
        return f"{item.title}\n{item.content_text or ''}".strip()

    async def _store_to_vector_db(self, item: UniversalItem, core_text: str):
        feature_text = "\n".join(part for part in (core_text, " ".join(item.tags)) if part)
        
        # 2. 调用 Embedding 服务
        embed_model_name = await self.ai.get_embedding_model_name()
        self.logger.info(f"🧠 [Embed] 正在使用 [{embed_model_name}] 计算向量...")
        vector = await self.ai.get_vector(feature_text)

        # 3. 写入数据库
        async with AsyncSessionLocal() as session:
            async with session.begin():
                data = {
                    "id": item.id,
                    "title": item.title,
                    "source_type": item.source_type,
                    "raw_link": str(item.raw_link),
                    "intent": item.intent,
                    "retention_days": item.retention_hours,
                    "content_text": item.content_text,
                    "summary": item.summary,
                    "tags": item.tags,
                    "metadata_extra": item.metadata_extra,
                    "embedding": vector # <--- 核心：存入向量！
                }

                stmt = insert(ItemORM).values(**data)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_={k: v for k, v in data.items() if k != 'id'}
                )
                await session.execute(stmt)

                if item.source_user_id:
                    link_stmt = insert(UserItemStateORM).values(
                        user_id=item.source_user_id,
                        item_id=item.id,
                        is_read=False,
                        is_watch_later=False,
                        is_favorited=False,
                    ).on_conflict_do_nothing(
                        index_elements=['user_id', 'item_id']
                    )
                    await session.execute(link_stmt)
        self.logger.info(f"✨ 向量数据已成功持久化: {item.id} (Vector Dim: {len(vector)})")

    async def _generate_summary(self, core_text: str):
        model = await self.ai.get_summary_model_name("short")
        self.logger.info(f"🤖 [LLM] 正在请求模型 [{model}] 生成摘要...")
        return await self.ai.generate_summary(core_text, length="short")

    async def _auto_tagging(self, core_text: str):
        model = await self.ai.get_tagging_model_name()
        self.logger.debug(f"DEBUG - [LLM] 正在使用 [{model}] 提取标签...")
        return await self.ai.extract_tags(core_text)

@broker.task(task_name="process_new_item")
async def process_new_item_task(item_dict: dict):
    item = UniversalItem.model_validate(item_dict)
    pipeline = IngestionPipeline()
    try:
        return await pipeline.process_item(item)
    except QuotaExceededException as exc:
        worker_log.error(f"❌ [CIRCUIT BREAKER] 入库分析已熔断: {item.id} | {exc.detail}")
        async with AsyncSessionLocal() as session:
            async with session.begin():
                existing_item = await session.get(ItemORM, item.id)
                if existing_item:
                    metadata = dict(existing_item.metadata_extra or {})
                    metadata["processing_status"] = "failed"
                    metadata["processing_error"] = exc.detail
                    await session.execute(
                        ItemORM.__table__.update()
                        .where(ItemORM.id == item.id)
                        .values(metadata_extra=metadata)
                    )
        return None
