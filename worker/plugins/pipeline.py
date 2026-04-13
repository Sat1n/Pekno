from shared.plugins.base import PluginContext
from shared.plugins.manager import plugin_manager
from shared.entities import UniversalItem
from shared.constants import PLATFORM_WHITELIST
from shared.credentials import get_user_credential, validate_required_credentials
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
import datetime
import re
import inspect


class MissingPluginCredentialError(RuntimeError):
    pass


async def _build_plugin_context_for_user(plugin_id: str, plugin, user_id: str | None):
    config_dict = {}
    for key, schema in plugin.manifest.get("settings_schema", {}).items():
        val = await ConfigManager.get_config(plugin_id, key, user_id=user_id)
        if val is not None:
            config_dict[key] = int(val) if schema.get("type") == "integer" else (val == "true" if schema.get("type") == "boolean" else val)
        else:
            config_dict[key] = schema.get("default")

    runtime_credentials = {}
    runtime_env = {}
    required_credentials = validate_required_credentials(plugin.manifest.get("required_credentials"))
    for platform in required_credentials:
        binding_enabled = await ConfigManager.get_config(
            plugin_id,
            ConfigKeys.credential_binding(platform),
            user_id=user_id,
        )
        credential = None
        if binding_enabled == "true" and user_id:
            credential = await get_user_credential(user_id, platform)
            if credential is None:
                raise MissingPluginCredentialError(
                    f"[{plugin_id}] Missing required global credential for platform '{platform}'"
                )

        if credential is None:
            legacy_key = PLATFORM_WHITELIST[platform].get("legacy_config_key")
            if legacy_key:
                legacy_value = await ConfigManager.get_config(plugin_id, legacy_key, user_id=user_id)
                if legacy_value:
                    runtime_credentials[platform] = legacy_value
                    config_key = PLATFORM_WHITELIST[platform].get("config_key")
                    if config_key and not config_dict.get(config_key):
                        config_dict[config_key] = legacy_value
                    continue

        if credential is not None:
            runtime_credentials[platform] = credential.token_value
            config_key = PLATFORM_WHITELIST[platform].get("config_key")
            env_var = PLATFORM_WHITELIST[platform].get("env_var")
            if config_key and not config_dict.get(config_key):
                config_dict[config_key] = credential.token_value
            if env_var:
                runtime_env[env_var] = credential.token_value

    import httpx
    http_client = None
    if plugin_id == "github_stars":
        from worker.plugins.github.client import GitHubClient
        token = config_dict.get("token")
        if not token:
            raise ValueError(f"[{plugin_id}] Token is not configured and link parsing cannot continue")
        http_client = GitHubClient(token)
    else:
        http_client = httpx.AsyncClient(timeout=15.0)

    return PluginContext(
        config=config_dict,
        http_client=http_client,
        logger=worker_log,
        credentials=runtime_credentials,
        env=runtime_env,
    )

@broker.task(task_name="run_plugin_pipeline")
async def run_plugin_pipeline_task(plugin_id: str, limit: int = None, user_id: str | None = None):
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

    try:
        ctx = await _build_plugin_context_for_user(plugin_id, plugin, user_id)
        config_dict = dict(ctx.config)

        if limit is not None:
            config_dict["sync_limit"] = limit

        raw_items = await plugin.fetch_data(ctx)
        if not raw_items:
            now_iso = datetime.datetime.now().isoformat()
            await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SUCCESSFUL_SYNC_TIME, now_iso, user_id=user_id)
            await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "success", user_id=user_id)
            if user_id:
                await create_notification_for_user(
                    user_id,
                    type="success",
                    category="plugin_sync",
                    title="手动同步已完成",
                    description=f"{plugin.manifest.get('name', plugin_id)} 没有新的内容。",
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
                    if cache_hit_count >= 3:
                        worker_log.info(f"🛑 [{plugin_id}] Incremental circuit triggered after consecutive cache hits. Ending sync early.")
                        break
                    continue

                cache_hit_count = 0

                ai_text = await plugin.extract_text_for_ai(ctx, raw_item)
                metadata_extra = raw_item.get('metadata_extra', {})
                final_metadata = normalized.get("metadata_extra", {})
                final_metadata.update(metadata_extra)
                final_metadata["has_long_summary"] = False

                item = UniversalItem(
                    id=normalized["id"],
                    title=normalized["title"],
                    source_type=normalized["source_type"],
                    raw_link=normalized["raw_link"],
                    content_text=normalized.get("content_text", ""),
                    intent=normalized.get("intent", "article"),
                    retention_hours=int(config_dict.get("retention_hours", normalized.get("retention_hours", 168))),
                    capabilities=["summarize"] if normalized.get("content_text") or ai_text else [],
                    metadata_extra=final_metadata,
                    auto_short_summary=bool(config_dict.get("auto_short_summary", normalized.get("auto_short_summary", False))),
                    source_user_id=user_id,
                )

                worker_log.info(f"📤 [{plugin_id}] Dispatching item to ingestion pipeline: {item.title}")
                await process_new_item_task.kiq(item.model_dump())

        worker_log.info(f"✅ [{plugin_id}] Sync dispatch completed. Processed {len(raw_items)} records.")
        now_iso = datetime.datetime.now().isoformat()
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SUCCESSFUL_SYNC_TIME, now_iso, user_id=user_id)
        await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "success", user_id=user_id)
        if user_id:
            await create_notification_for_user(
                user_id,
                type="success",
                category="plugin_sync",
                title="手动同步已完成",
                description=f"{plugin.manifest.get('name', plugin_id)} 已完成同步。",
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
                title="手动同步失败",
                description=str(e)[:160],
                related_plugin_id=plugin_id,
            )
    finally:
        now_iso = datetime.datetime.now().isoformat()
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
        ctx = await _build_plugin_context_for_user(plugin_id, plugin, user_id)
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
        if preferred_locale:
            final_metadata["preferred_locale"] = preferred_locale

        retention_value = retention_days
        if retention_value == -1:
            retention_value = int(ctx.config.get("retention_hours", normalized.get("retention_hours", 168)))

        item = UniversalItem(
            id=normalized["id"],
            title=normalized["title"],
            source_type=normalized["source_type"],
            raw_link=normalized["raw_link"],
            content_text=normalized.get("content_text", ""),
            intent=normalized.get("intent", "article"),
            retention_hours=retention_value,
            capabilities=["summarize"] if normalized.get("content_text") or ai_text else [],
            metadata_extra=final_metadata,
            auto_short_summary=bool(ctx.config.get("auto_short_summary", normalized.get("auto_short_summary", False))),
            source_user_id=user_id,
        )

        worker_log.info(f"📤 [{plugin_id}] Dispatching single parsed item to ingestion pipeline: {item.title}")
        await process_new_item_task.kiq(item.model_dump())
    except Exception as e:
        worker_log.error(f"❌ [{plugin_id}] Single-item parsing task failed: {e}")
        raise
    finally:
        close_method = getattr(ctx.http, "aclose", None)
        if close_method:
            await close_method()


@broker.task(task_name="summarize_repo")
async def summarize_repo_task(
    item_id: str,
    task_id: str,
    user_id: str | None = None,
    preferred_locale: str | None = None,
):
    """
    Backward-compatible AI summary task entrypoint kept for frontend compatibility.
    """
    plugin_id = "github_stars"
    worker_log.info(f"🚀 Starting AI summary task: {task_id} for item {item_id}")
    
    try:
        async with AsyncSessionLocal() as session:
            result = await session.execute(ItemORM.__table__.select().where(ItemORM.id == item_id))
            item = result.fetchone()
            if not item: return
                
        plugin = plugin_manager.get_plugin(plugin_id)
        if not plugin: return

        token = await ConfigManager.get_config(plugin_id, ConfigKeys.TOKEN)
        from worker.plugins.github.client import GitHubClient
        ctx = PluginContext(
            config={},
            http_client=GitHubClient(token) if token else None,
            logger=worker_log
        )
        
        repo_match = re.search(r'github\.com/([^/]+)/([^/]+)', item.raw_link or "")
        raw_data = {
            "name": repo_match.group(2) if repo_match else item.title,
            "owner": {"login": repo_match.group(1) if repo_match else ""},
            "description": item.content_text,
            "metadata_extra": item.metadata_extra or {}
        }

        if item.source_type == "github_star" and repo_match:
            text_to_summarize = await plugin.extract_text_for_ai(ctx, raw_data)
        else:
            text_to_summarize = "\n\n".join(
                part for part in [
                    f"标题：{item.title}" if item.title else "",
                    f"简介：{item.content_text or item.summary}" if (item.content_text or item.summary) else "",
                ]
                if part
            )
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
            title="AI 总结已完成",
            description=f"{item.title or '该内容'} 已生成 AI 总结。",
            related_item_id=item_id,
        )
            
    except QuotaExceededException as e:
        worker_log.error(f"❌ [CIRCUIT BREAKER] AI summary task blocked: {e.detail}")
        await create_notification_for_user(
            user_id,
            type="error",
            category="summary",
            title="AI 总结失败",
            description="API 限额可能已用尽，请联系管理员。",
            related_item_id=item_id,
        )
        raise
    except Exception as e:
        worker_log.error(f"❌ AI summary task failed: {e}")
        await create_notification_for_user(
            user_id,
            type="error",
            category="summary",
            title="AI 总结失败",
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
