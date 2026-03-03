from hub.core.models import UniversalItem
from hub.core.logger import worker_log
from worker.broker import broker

class IngestionPipeline:
    def __init__(self):
        self.logger = worker_log

    async def process_item(self, item: UniversalItem):
        self.logger.info(f">>> 接收到新任务: {item.title} (ID: {item.id})")

        # DEBUG 记录插件私有数据，防止 metadata_extra 丢失字段
        self.logger.debug(f"DEBUG - [Entry] 插件私有元数据: {item.metadata_extra}")

        try:
            # 1. 自动分类
            if not item.tags:
                self.logger.debug(f"正在为 {item.id} 进行 AI 自动打标签...")
                item.tags = await self._auto_tagging(item)

            # 2. 摘要生成
            if item.capabilities and "summarize" in item.capabilities:
                self.logger.info(f"触发 AI 总结服务: {item.id}")
                item.summary = await self._generate_summary(item)

            # 3. 向量存储
            self.logger.debug(f"正在执行向量化入库: {item.id}")
            await self._store_to_vector_db(item)
            
            self.logger.info(f"成功存入 Iris 记忆库: {item.id}")
            return item

        except Exception as e:
            self.logger.error(f"处理任务失败 {item.id}: {str(e)}", exc_info=True)
            raise e

    async def _auto_tagging(self, item: UniversalItem):
        # 实际开发时这里会调用 LLM
        return ["AI-Auto", item.source_type]

    async def _generate_summary(self, item: UniversalItem):
        # 实际开发时这里会调用 LLM
        return f"这是关于 {item.title} 的简要总结..."

    async def _store_to_vector_db(self, item: UniversalItem):
        # 这里对接 pgvector
        pass

@broker.task(task_name="process_new_item")
async def process_new_item_task(item_dict: dict):
    item = UniversalItem.model_validate(item_dict)
    pipeline = IngestionPipeline()
    return await pipeline.process_item(item)