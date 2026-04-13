from shared.plugins.base import PluginContext
from shared.plugins.manager import plugin_manager
from shared.entities import UniversalItem
from hub.core.notifications import create_notification_for_user
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


async def _build_plugin_context_for_user(plugin_id: str, plugin, user_id: str | None):
    config_dict = {}
    for key, schema in plugin.manifest.get("settings_schema", {}).items():
        val = await ConfigManager.get_config(plugin_id, key, user_id=user_id)
        if val is not None:
            config_dict[key] = int(val) if schema.get("type") == "integer" else (val == "true" if schema.get("type") == "boolean" else val)
        else:
            config_dict[key] = schema.get("default")

    import httpx
    http_client = None
    if plugin_id == "github_stars":
        from worker.plugins.github.client import GitHubClient
        token = config_dict.get("token")
        if not token:
            raise ValueError(f"[{plugin_id}] 未配置 Token，无法解析链接")
        http_client = GitHubClient(token)
    else:
        http_client = httpx.AsyncClient(timeout=15.0)

    return PluginContext(
        config=config_dict,
        http_client=http_client,
        logger=worker_log
    )

@broker.task(task_name="run_plugin_pipeline")
async def run_plugin_pipeline_task(plugin_id: str, limit: int = None, user_id: str | None = None):
    """
    通用化：运行指定插件的同步流水线
    """
    # 先尝试获取，如果不存在可能因为 Worker 刚启动或热重载延迟，尝试重新加载一次
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        worker_log.warning(f"⚠️ 初次未找到插件 {plugin_id}，尝试重新加载注册表...")
        async with AsyncSessionLocal() as session:
            await plugin_manager.load_enabled_plugins(session)
        plugin = plugin_manager.get_plugin(plugin_id)
        
    if not plugin:
        worker_log.error(f"❌ 找不到插件: {plugin_id} (即使重载后)")
        return

    # 状态锁检查
    status = await ConfigManager.get_config(plugin_id, ConfigKeys.SYNC_STATUS, user_id=user_id)
    if status == "running":
        worker_log.warning(f"⚠️ [{plugin_id}] 同步任务已经在运行中，跳过本次执行")
        return

    await ConfigManager.set_config(plugin_id, ConfigKeys.SYNC_STATUS, "running", user_id=user_id)
    await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_RESULT, "running", user_id=user_id)
    await ConfigManager.set_config(plugin_id, ConfigKeys.LAST_SYNC_ERROR, "", user_id=user_id)

    try:
        # 获取基础配置字典
        ctx = await _build_plugin_context_for_user(plugin_id, plugin, user_id)
        config_dict = dict(ctx.config)

        # 覆写 limit
        if limit is not None:
            config_dict["sync_limit"] = limit

        # 1. 抓取原始数据
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
            # 2. 遍历处理入库流水线
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
                    worker_log.info(f"⏭️ [{plugin_id}] 命中历史数据，跳过: {normalized['title']} (连续命中 {cache_hit_count})")
                    if cache_hit_count >= 3:
                        worker_log.info(f"🛑 [{plugin_id}] 连续命中历史数据，触发增量熔断，提前结束同步。")
                        break
                    continue

                cache_hit_count = 0

                # 3. 为新数据补充附加文本与元数据
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

                worker_log.info(f"📤 [{plugin_id}] 发送至 Pipeline 处理: {item.title}")
                await process_new_item_task.kiq(item.model_dump())

        worker_log.info(f"✅ [{plugin_id}] 同步指令下发完毕，共处理 {len(raw_items)} 条记录。")
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

    except Exception as e:
        worker_log.error(f"❌ [{plugin_id}] 任务执行出错: {e}")
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
async def parse_single_plugin_item_task(plugin_id: str, url: str, user_id: str, retention_days: int = -1):
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        worker_log.warning(f"⚠️ 初次未找到插件 {plugin_id}，尝试重新加载注册表...")
        async with AsyncSessionLocal() as session:
            await plugin_manager.load_enabled_plugins(session)
        plugin = plugin_manager.get_plugin(plugin_id)

    if not plugin:
        worker_log.error(f"❌ 找不到插件: {plugin_id} (单条解析失败)")
        return

    ctx = await _build_plugin_context_for_user(plugin_id, plugin, user_id)
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

        worker_log.info(f"📤 [{plugin_id}] 单条解析结果发送至 Pipeline: {item.title}")
        await process_new_item_task.kiq(item.model_dump())
    except Exception as e:
        worker_log.error(f"❌ [{plugin_id}] 单条解析任务失败: {e}")
        raise
    finally:
        close_method = getattr(ctx.http, "aclose", None)
        if close_method:
            await close_method()


@broker.task(task_name="summarize_repo")
async def summarize_repo_task(item_id: str, task_id: str, user_id: str | None = None):
    """
    临时预留：AI 补总结调度任务（依然由前端原样调用，所以暂时保留名字，内部改用 plugin manager 取）
    """
    plugin_id = "github_stars"
    worker_log.info(f"🚀 开始 AI 总结任务: {task_id} for item {item_id}")
    
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
                worker_log.info(f"⏭️ 跳过 AI 总结：条目缺少可总结文本 {item_id}")
                return
        
        from hub.core.llm.service import LLMManager
        ai = LLMManager()
        summary = await ai.generate_summary(text_to_summarize, length="long")

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
            
    except Exception as e:
        worker_log.error(f"❌ AI 总结任务失败: {e}")
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

    worker_log.info("🔄 收到热重载指令，正在刷新 Worker 插件内存...")
    async with AsyncSessionLocal() as session:
        plugin_manager.plugins.clear() # 物理清空旧实例
        await plugin_manager.load_enabled_plugins(session)
