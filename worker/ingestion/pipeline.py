from shared.entities import AIProcessingStatus, UniversalItem
from shared.logger import worker_log
from worker.broker import broker
from shared.database import AsyncSessionLocal  # 导入会话工厂
from shared.models import ItemORM, UserItemStateORM     # 导入数据库模型
from sqlalchemy.dialects.postgresql import insert
from hub.core.billing import QuotaExceededException
from hub.core.llm.service import LLMManager
from worker.plugins.runtime import (
    build_item_raw_data,
    build_plugin_context_for_user,
    close_plugin_context,
    fallback_text_for_summary,
    find_plugin_by_source_type,
)

class IngestionPipeline:
    def __init__(self):
        self.logger = worker_log
        self.ai = LLMManager()
        self.current_item: UniversalItem | None = None
        

    async def process_item(self, item: UniversalItem):
        self.current_item = item
        self.logger.info(f">>> Received new ingestion task: {item.title} (ID: {item.id})")

        self.logger.debug(f"DEBUG - [Entry] Plugin metadata payload: {item.metadata_extra}")

        try:
            core_text = self._build_core_text(item)
            core_text = await self._prepare_core_text(item, core_text)

            if item.auto_short_summary and item.capabilities and "summarize" in item.capabilities:
                item.summary = await self._generate_summary(core_text)
            else:
                item.summary = item.content_text or item.title
                self.logger.info(
                    f"⏭️ Skipping AI short summary: {item.title} "
                    f"(source={item.source_type}, auto_short_summary={item.auto_short_summary})"
                )

            item.tags = await self._auto_tagging(core_text)

            # 3. 核心：执行数据库持久化
            await self._store_to_vector_db(item, core_text)
            
            self.logger.info(f"✅ Successfully persisted item to Postgres: {item.id}")
            return item
        except Exception as e:
            self.logger.error(f"❌ Failed to ingest item {item.id}: {str(e)}", exc_info=True)
            raise e
    
    def _build_core_text(self, item: UniversalItem) -> str:
        return f"{item.title}\n{item.content_text or ''}".strip()

    def _preferred_locale(self, item: UniversalItem) -> str | None:
        return (item.metadata_extra or {}).get("preferred_locale")

    async def _store_to_vector_db(self, item: UniversalItem, core_text: str):
        feature_text = "\n".join(part for part in (core_text, " ".join(item.tags)) if part)
        
        # 2. 调用 Embedding 服务
        embed_model_name = await self.ai.get_embedding_model_name()
        self.logger.info(f"🧠 [Embed] Computing vector with model [{embed_model_name}]...")
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
                    "embedding": vector, # <--- 核心：存入向量！
                    "ai_processing_status": AIProcessingStatus.completed.value,
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
        self.logger.info(f"✨ Vector data persisted successfully: {item.id} (Vector Dim: {len(vector)})")

    async def _prepare_core_text(self, item: UniversalItem, core_text: str) -> str:
        if (item.metadata_extra or {}).get("ai_text_extracted"):
            return core_text

        plugin_id, plugin = await find_plugin_by_source_type(item.source_type)
        if not plugin_id or not plugin:
            return core_text

        ctx = None
        try:
            ctx = await build_plugin_context_for_user(plugin_id, plugin, item.source_user_id)
            raw_data = build_item_raw_data(item)
            ai_text = await plugin.extract_text_for_ai(ctx, raw_data)
            if raw_data.get("metadata_extra"):
                item.metadata_extra.update(raw_data["metadata_extra"])
            if ai_text and ai_text.strip():
                item.content_text = ai_text.strip()
                return self._build_core_text(item)
        except Exception as exc:
            self.logger.warning(
                "⚠️ Plugin AI extraction failed during ingestion; falling back to stored content. "
                "item=%s plugin=%s error=%s",
                item.id,
                plugin_id,
                exc,
            )
        finally:
            if ctx is not None:
                await close_plugin_context(ctx)

        return fallback_text_for_summary(item) or core_text

    async def _generate_summary(self, core_text: str):
        model = await self.ai.get_summary_model_name("short")
        self.logger.info(f"🤖 [LLM] Requesting summary generation from model [{model}]...")
        try:
            return await self.ai.generate_summary(
                core_text,
                length="short",
                preferred_locale=self._preferred_locale(self.current_item) if self.current_item else None,
            )
        except QuotaExceededException:
            raise
        except Exception as exc:
            self.logger.warning(
                "⚠️ Short summary generation failed; falling back to raw text. model=%s error=%s",
                model,
                exc,
            )
            return self.current_item.content_text or self.current_item.title if self.current_item else core_text

    async def _auto_tagging(self, core_text: str):
        model = await self.ai.get_tagging_model_name()
        self.logger.debug(f"DEBUG - [LLM] Extracting tags with model [{model}]...")
        try:
            return await self.ai.extract_tags(
                core_text,
                preferred_locale=self._preferred_locale(self.current_item) if self.current_item else None,
            )
        except QuotaExceededException:
            raise
        except Exception as exc:
            self.logger.warning(
                "⚠️ Auto-tagging failed; continuing without tags. model=%s error=%s",
                model,
                exc,
            )
            return []

@broker.task(task_name="process_new_item")
async def process_new_item_task(item_dict: dict):
    item = UniversalItem.model_validate(item_dict)
    pipeline = IngestionPipeline()
    try:
        return await pipeline.process_item(item)
    except QuotaExceededException as exc:
        worker_log.error(f"❌ [CIRCUIT BREAKER] Ingestion analysis blocked: {item.id} | {exc.detail}")
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
                        .values(
                            metadata_extra=metadata,
                            ai_processing_status=AIProcessingStatus.pending_ai.value,
                        )
                    )
        return None
    except Exception as exc:
        worker_log.error(f"❌ Ingestion analysis failed: {item.id} | {exc}")
        async with AsyncSessionLocal() as session:
            async with session.begin():
                existing_item = await session.get(ItemORM, item.id)
                if existing_item:
                    metadata = dict(existing_item.metadata_extra or {})
                    metadata["processing_status"] = "failed"
                    metadata["processing_error"] = str(exc)
                    await session.execute(
                        ItemORM.__table__.update()
                        .where(ItemORM.id == item.id)
                        .values(
                            metadata_extra=metadata,
                            ai_processing_status=AIProcessingStatus.pending_ai.value,
                        )
                    )
        return None
