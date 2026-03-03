from hub.core.models import UniversalItem
from hub.core.logger import worker_log
from worker.broker import broker
from hub.core.database import AsyncSessionLocal  # 导入会话工厂
from hub.core.database_models import ItemORM     # 导入数据库模型
from sqlalchemy.dialects.postgresql import insert
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
            # 1. 自动分类 (Mock)
            if not item.tags:
                item.tags = await self._auto_tagging(item)

            # 2. 摘要生成 (Mock)
            if item.capabilities and "summarize" in item.capabilities:
                item.summary = await self._generate_summary(item)

            # 3. 核心：执行数据库持久化
            await self._store_to_vector_db(item)
            
            self.logger.info(f"✅ 成功同步至 Postgres: {item.id}")
            return item
        except Exception as e:
            self.logger.error(f"❌ 入库失败 {item.id}: {str(e)}", exc_info=True)
            raise e
    
    async def _store_to_vector_db(self, item: UniversalItem):
        # 1. 生成特征文本：把标题、摘要、标签揉在一起，这就是搜索的“依据”
        feature_text = f"{item.title}\n{item.summary}\n{' '.join(item.tags)}"
        
        # 2. 调用 Embedding 服务
        self.logger.info(f"🧠 [Embed] 正在使用 [{self.ai.embed_model_name}] 计算向量...")
        vector = await self.ai.embed.get_vector(feature_text)

        # 3. 写入数据库
        async with AsyncSessionLocal() as session:
            async with session.begin():
                data = {
                    "id": item.id,
                    "title": item.title,
                    "source_type": item.source_type,
                    "raw_link": str(item.raw_link),
                    "intent": item.intent.value,
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
        self.logger.info(f"✨ 向量数据已成功持久化: {item.id} (Vector Dim: {len(vector)})")

    async def _generate_summary(self, item: UniversalItem):
        model = self.ai.model_name
        self.logger.info(f"🤖 [LLM] 正在请求模型 [{model}] 生成摘要...")
        return await self.ai.llm.provider.generate_summary(item.content_text or item.title)

    async def _auto_tagging(self, item: UniversalItem):
        model = self.ai.model_name
        self.logger.debug(f"DEBUG - [LLM] 正在使用 [{model}] 提取标签...")
        return await self.ai.llm.provider.extract_tags(item.title)

@broker.task(task_name="process_new_item")
async def process_new_item_task(item_dict: dict):
    item = UniversalItem.model_validate(item_dict)
    pipeline = IngestionPipeline()
    return await pipeline.process_item(item)