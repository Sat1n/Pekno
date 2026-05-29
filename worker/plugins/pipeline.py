from shared.plugins.manager import plugin_manager
from shared.entities import AIProcessingStatus, UniversalItem
from hub.core.notifications import create_notification_for_user
from hub.core.billing import QuotaExceededException
from worker.ingestion.pipeline import process_new_item_task
from shared.logger import worker_log
from worker.broker import broker
from shared.config import ConfigManager, ConfigKeys
from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
import inspect
from shared.time_utils import now_in_app_timezone_naive
from worker.plugins.runtime import (
    MissingPluginCredentialError,
    build_item_raw_data,
    build_plugin_context_for_user,
    close_plugin_context,
    fallback_text_for_summary,
    resolve_sync_fetch_mode,
)


async def _store_lightweight_item(
    normalized: dict[str, Any],
    metadata_extra: dict[str, Any] | None,
    user_id: str | None,
    retention_hours: int,
    plugin_id: str | None = None,
) -> None:
    item_id = normalized["id"]
    now = now_in_app_timezone_naive()
    metadata = dict(metadata_extra or {})
    metadata.setdefault("has_long_summary", False)
    metadata["processing_status"] = AIProcessingStatus.pending_ai.value

    data = {
        "id": item_id,
        "title": normalized.get("title", ""),
        "source_type": normalized["source_type"],
        "plugin_id": plugin_id,
        "created_at": now,
        "raw_link": normalized.get("raw_link", "#"),
        "intent": normalized.get("intent", "article"),
        "retention_days": retention_hours,
        "content_text": normalized.get("content_text", ""),
        "summary": normalized.get("summary") or normalized.get("content_text") or normalized.get("title", ""),
        "tags": normalized.get("tags") or [],
        "metadata_extra": metadata,
        "ai_processing_status": AIProcessingStatus.pending_ai.value,
        "updated_at": now,
    }

    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = insert(ItemORM).values(**data).on_conflict_do_update(
                index_elements=["id"],
                set_={k: v for k, v in data.items() if k not in {"id", "created_at"}},
            )
            await session.execute(stmt)

            if user_id:
                link_stmt = insert(UserItemStateORM).values(
                    user_id=user_id,
                    item_id=item_id,
                    is_read=False,
                    is_watch_later=False,
                    is_favorited=False,
                ).on_conflict_do_nothing(
                    index_elements=["user_id", "item_id"]
                )
                await session.execute(link_stmt)


async def _has_existing_plugin_items(source_type: str | None, user_id: str | None) -> bool:
    if not source_type:
        return False

    async with AsyncSessionLocal() as session:
        if user_id:
            result = await session.execute(
                select(ItemORM.id)
                .join(UserItemStateORM, UserItemStateORM.item_id == ItemORM.id)
                .where(
                    ItemORM.source_type == source_type,
                    UserItemStateORM.user_id == user_id,
                )
                .limit(1)
            )
        else:
            result = await session.execute(
                select(ItemORM.id)
                .where(ItemORM.source_type == source_type)
                .limit(1)
            )
        return result.scalar_one_or_none() is not None


@broker.task(task_name="run_plugin_pipeline")
async def run_plugin_pipeline_task(
    plugin_id: str,
    limit: int = None,
    user_id: str | None = None,
    sync_mode: str = "manual",
    preferred_locale: str | None = None,
):
    """
    Run the generic sync pipeline for a specific plugin.
    """
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        worker_log.warning(f"⚠️ Plugin {plugin_id} was not found on first lookup. Reloading registry and retrying...")
        async with AsyncSessionLocal() as session:
            await plugin_manager.load_enabled_plugins(session)
        plugin = plugin_manager.get_plugin(plugin_id)
        
    if not plugin:
        worker_log.error(f"❌ Plugin not found after reload: {plugin_id}")
        return

    status = await ConfigManager.get_config(plugin_id, ConfigKeys.SYNC_STATUS, user_id=user_id)
    if status == "running":
        worker_log.warning(f"⚠️ [{plugin_id}] Sync task is already running. Skipping this execution.")
        return

    await ConfigManager.set_config(plugin_id, ConfigKeys.SYNC_STATUS, "running", user_id=user_id)
    await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "running", user_id=user_id)
    await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_ERROR, "", user_id=user_id)

    ctx = None
    try:
        ctx = await build_plugin_context_for_user(plugin_id, plugin, user_id)
        config_dict = dict(ctx.config)

        if limit is not None:
            config_dict["sync_limit"] = limit
        incremental_ai_sync = bool(config_dict.get(ConfigKeys.ENABLE_INCREMENTAL_AI_SYNC, False))
        source_type = plugin.manifest.get("source_type")
        has_existing_items = await _has_existing_plugin_items(source_type, user_id)
        fetch_mode, disable_cache_hit_breaker = resolve_sync_fetch_mode(
            incremental_ai_sync=incremental_ai_sync,
            sync_mode=sync_mode,
            has_existing_items=has_existing_items,
        )
        config_dict["_pekno_sync_mode"] = fetch_mode
        ctx.config = config_dict
        worker_log.info(
            f"🔁 [{plugin_id}] Sync mode resolved: trigger={sync_mode}, "
            f"fetch={fetch_mode}, breaker_disabled={disable_cache_hit_breaker}"
        )

        raw_items = await plugin.fetch_data(ctx)
        if not raw_items:
            now_iso = now_in_app_timezone_naive().isoformat()
            await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SUCCESSFUL_SYNC_TIME, now_iso, user_id=user_id)
            await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "success", user_id=user_id)
            await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_ERROR, "", user_id=user_id)
            if user_id:
                await create_notification_for_user(
                    user_id,
                    type="success",
                    category="plugin_sync",
                    title="Manual sync completed",
                    description=f"{plugin.manifest.get('name', plugin_id)} has no new content.",
                    related_plugin_id=plugin_id,
                )
            return

        cache_hit_count = 0
        async with AsyncSessionLocal() as session:
            for raw_item in raw_items:
                normalized = plugin.normalize_item(raw_item)
                item_id = normalized["id"]

                existing_item = await session.execute(
                    select(ItemORM.id).where(ItemORM.id == item_id)
                )
                existing_item_id = existing_item.scalar_one_or_none()

                if existing_item_id is not None:
                    if user_id:
                        await session.execute(
                            insert(UserItemStateORM).values(
                                user_id=user_id,
                                item_id=item_id,
                                is_read=False,
                                is_watch_later=False,
                                is_favorited=False,
                            ).on_conflict_do_nothing(
                                index_elements=["user_id", "item_id"]
                            )
                    )
                    cache_hit_count += 1
                    worker_log.info(
                        f"⏭️ [{plugin_id}] Existing item hit, skipping: {normalized['title']} "
                        f"(consecutive hits: {cache_hit_count})"
                    )
                    if not disable_cache_hit_breaker and cache_hit_count >= 3:
                        worker_log.info(f"🛑 [{plugin_id}] Incremental circuit triggered after consecutive cache hits. Ending sync early.")
                        break
                    continue

                cache_hit_count = 0

                metadata_extra = raw_item.get('metadata_extra', {})
                final_metadata = normalized.get("metadata_extra", {})
                final_metadata.update(metadata_extra)
                final_metadata["has_long_summary"] = False

                if preferred_locale:
                    final_metadata["preferred_locale"] = preferred_locale

                if incremental_ai_sync:
                    await _store_lightweight_item(
                        normalized,
                        final_metadata,
                        user_id=user_id,
                        retention_hours=int(config_dict.get("retention_hours", normalized.get("retention_hours", 168))),
                        plugin_id=plugin_id,
                    )
                    worker_log.info(f"📥 [{plugin_id}] Stored lightweight item for AI sweep: {normalized['title']}")
                    continue

                ai_text = await plugin.extract_text_for_ai(ctx, raw_item)
                if ai_text and ai_text.strip():
                    final_metadata["ai_text_extracted"] = True

                item = UniversalItem(
                    id=normalized["id"],
                    title=normalized.get("title", ""),
                    source_type=normalized["source_type"],
                    plugin_id=plugin_id,
                    raw_link=normalized.get("raw_link", "#"),
                    content_text=ai_text.strip() if ai_text and ai_text.strip() else normalized.get("content_text", ""),
                    intent=normalized.get("intent", "article"),
                    retention_hours=int(config_dict.get("retention_hours", normalized.get("retention_hours", 168))),
                    capabilities=["summarize"] if normalized.get("content_text") or ai_text else [],
                    metadata_extra=final_metadata,
                    auto_short_summary=bool(config_dict.get("auto_short_summary", normalized.get("auto_short_summary", False))),
                    source_user_id=user_id,
                    ai_processing_status=AIProcessingStatus.processing,
                )

                worker_log.info(f"📤 [{plugin_id}] Dispatching item to ingestion pipeline: {item.title}")
                await process_new_item_task.kiq(item.model_dump())

            await session.commit()

        worker_log.info(f"✅ [{plugin_id}] Sync dispatch completed. Processed {len(raw_items)} records.")
        now_iso = now_in_app_timezone_naive().isoformat()
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SUCCESSFUL_SYNC_TIME, now_iso, user_id=user_id)
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "success", user_id=user_id)
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_ERROR, "", user_id=user_id)
        if user_id:
            await create_notification_for_user(
                user_id,
                type="success",
                category="plugin_sync",
                title="Manual sync completed",
                description=f"{plugin.manifest.get('name', plugin_id)} finished syncing successfully.",
                related_plugin_id=plugin_id,
            )

    except MissingPluginCredentialError as e:
        worker_log.warning(f"Skipping plugin execution due to missing credential: {e}")
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "warning", user_id=user_id)
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_ERROR, str(e)[:500], user_id=user_id)
    except Exception as e:
        worker_log.error(f"❌ [{plugin_id}] Sync task failed: {e}")
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "error", user_id=user_id)
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_ERROR, str(e)[:500], user_id=user_id)
        if user_id:
            await create_notification_for_user(
                user_id,
                type="error",
                category="plugin_sync",
                title="Manual sync failed",
                description=str(e)[:160],
                related_plugin_id=plugin_id,
            )
    finally:
        if ctx is not None:
            await close_plugin_context(ctx)
        now_iso = now_in_app_timezone_naive().isoformat()
        await ConfigManager.set_config(plugin_id, ConfigKeys.SYNC_STATUS, "idle", user_id=user_id)
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_TIME, now_iso, user_id=user_id)


@broker.task(task_name="parse_single_plugin_item")
async def parse_single_plugin_item_task(
    plugin_id: str,
    url: str,
    user_id: str,
    retention_days: int = -1,
    preferred_locale: str | None = None,
):
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        worker_log.warning(f"⚠️ Plugin {plugin_id} was not found on first lookup. Reloading registry and retrying...")
        async with AsyncSessionLocal() as session:
            await plugin_manager.load_enabled_plugins(session)
        plugin = plugin_manager.get_plugin(plugin_id)

    if not plugin:
        worker_log.error(f"❌ Plugin not found for single-item parsing: {plugin_id}")
        return

    try:
        ctx = await build_plugin_context_for_user(plugin_id, plugin, user_id)
    except MissingPluginCredentialError as e:
        worker_log.warning(f"Skipping single-item parsing due to missing credential: {e}")
        raise ValueError(str(e))
    try:
        parse_signature = inspect.signature(plugin.parse_single_item)
        if "ctx" in parse_signature.parameters:
            parsed_item = await plugin.parse_single_item(url, ctx)
        else:
            parsed_item = await plugin.parse_single_item(url)

        pipeline_raw_data = parsed_item.pop("_pipeline_raw_data", None)
        if pipeline_raw_data is not None:
            normalized = plugin.normalize_item(pipeline_raw_data)
            ai_text = await plugin.extract_text_for_ai(ctx, pipeline_raw_data)
            raw_metadata = dict(pipeline_raw_data.get("metadata_extra") or {})
        else:
            normalized = parsed_item
            ai_text = normalized.get("content_text", "") or ""
            raw_metadata = {}

        normalized["raw_link"] = normalized.get("raw_link") or url
        final_metadata = dict(normalized.get("metadata_extra") or {})
        final_metadata.update(raw_metadata)
        final_metadata["has_long_summary"] = False
        if ai_text and ai_text.strip():
            final_metadata["ai_text_extracted"] = True
        if preferred_locale:
            final_metadata["preferred_locale"] = preferred_locale

        retention_value = retention_days
        if retention_value == -1:
            retention_value = int(ctx.config.get("retention_hours", normalized.get("retention_hours", 168)))

        item = UniversalItem(
            id=normalized["id"],
            title=normalized.get("title", ""),
            source_type=normalized["source_type"],
            plugin_id=plugin_id,
            raw_link=normalized.get("raw_link", "#"),
            content_text=ai_text.strip() if ai_text and ai_text.strip() else normalized.get("content_text", ""),
            intent=normalized.get("intent", "article"),
            retention_hours=retention_value,
            capabilities=["summarize"] if normalized.get("content_text") or ai_text else [],
            metadata_extra=final_metadata,
            auto_short_summary=bool(ctx.config.get("auto_short_summary", normalized.get("auto_short_summary", False))),
            source_user_id=user_id,
            ai_processing_status=AIProcessingStatus.processing,
        )

        worker_log.info(f"📤 [{plugin_id}] Dispatching single parsed item to ingestion pipeline: {item.title}")
        await process_new_item_task.kiq(item.model_dump())
    except Exception as e:
        worker_log.error(f"❌ [{plugin_id}] Single-item parsing task failed: {e}")
        raise
    finally:
        await close_plugin_context(ctx)


@broker.task(task_name="summarize_repo")
async def summarize_repo_task(
    item_id: str,
    task_id: str,
    user_id: str | None = None,
    preferred_locale: str | None = None,
):
    """
    Backward-compatible task entrypoint for long-form item summaries.
    """
    worker_log.info(f"🚀 Starting AI summary task: {task_id} for item {item_id}")
    
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(ItemORM.__table__.select().where(ItemORM.id == item_id))
            item = result.fetchone()
            if not item: return

        plugin_id = item.plugin_id
        plugin = plugin_manager.get_plugin(plugin_id) if plugin_id else None
        raw_data = build_item_raw_data(item)
        text_to_summarize = ""

        if plugin_id and plugin:
            ctx = None
            try:
                ctx = await build_plugin_context_for_user(plugin_id, plugin, user_id)
                text_to_summarize = await plugin.extract_text_for_ai(ctx, raw_data)
            except Exception as exc:
                worker_log.warning(
                    "⚠️ Plugin AI text extraction failed; falling back to stored content. "
                    "item_id=%s plugin=%s error=%s",
                    item_id,
                    plugin_id,
                    exc,
                )
            finally:
                if ctx is not None:
                    await close_plugin_context(ctx)

        if not text_to_summarize.strip():
            text_to_summarize = fallback_text_for_summary(item)
        if not text_to_summarize.strip():
            worker_log.info(f"⏭️ Skipping AI summary because the item has no summarizable text: {item_id}")
            return
        
        from hub.core.llm.service import LLMManager
        ai = LLMManager()
        locale = preferred_locale or (item.metadata_extra or {}).get("preferred_locale")
        summary = await ai.generate_summary(text_to_summarize, length="long", preferred_locale=locale)

        async with AsyncSessionLocal() as session:
            new_metadata_extra = dict(item.metadata_extra) if item.metadata_extra else {}
            # Integrate injected variables collected during extract_text_for_ai
            new_metadata_extra.update(raw_data.get("metadata_extra", {}))
            new_metadata_extra["has_long_summary"] = True
            new_metadata_extra["long_summary"] = summary
            if plugin_id:
                new_metadata_extra["summary_plugin_id"] = plugin_id
            
            await session.execute(
                ItemORM.__table__.update()
                .where(ItemORM.id == item_id)
                .values(
                    metadata_extra=new_metadata_extra
                )
            )
            await session.commit()
        await create_notification_for_user(
            user_id,
            type="success",
            category="summary",
            title="AI summary completed",
            description=f"AI summary is ready for {item.title or 'this item'}.",
            related_item_id=item_id,
        )
            
    except QuotaExceededException as e:
        worker_log.error(f"❌ [CIRCUIT BREAKER] AI summary task blocked: {e.detail}")
        await create_notification_for_user(
            user_id,
            type="error",
            category="summary",
            title="AI summary failed",
            description="The API quota may be exhausted. Please contact an administrator.",
            related_item_id=item_id,
        )
        raise
    except Exception as e:
        worker_log.error(f"❌ AI summary task failed: {e}")
        await create_notification_for_user(
            user_id,
            type="error",
            category="summary",
            title="AI summary failed",
            description=str(e)[:160],
            related_item_id=item_id,
        )
        raise

@broker.task(task_name="reload_system_plugins")
async def reload_system_plugins_task():
    from shared.database import AsyncSessionLocal
    from shared.plugins.manager import plugin_manager
    from shared.logger import worker_log

    worker_log.info("🔄 Hot reload command received. Refreshing Worker plugin registry...")
    async with AsyncSessionLocal() as session:
        plugin_manager.plugins.clear() # 物理清空旧实例
        await plugin_manager.load_enabled_plugins(session)
