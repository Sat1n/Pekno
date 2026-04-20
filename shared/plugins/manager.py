from typing import Dict, List, Optional
import importlib
import inspect
from copy import deepcopy
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from shared.plugins.base import BasePlugin
from shared.credentials import validate_required_credentials
from shared.logger import app_log
from shared.models import PluginRegistryORM

class PluginManager:
    """插件管理器 (单例)"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PluginManager, cls).__new__(cls)
            cls._instance.plugins = {}
        return cls._instance

    def _infer_default_auto_short_summary(self, manifest: Dict) -> bool:
        text = " ".join(
            str(manifest.get(key, "")).lower()
            for key in ("id", "name", "description")
        )
        return not any(keyword in text for keyword in ("video", "bilibili", "影音", "视频"))

    def _get_framework_default(self, manifest: Dict, key: str, fallback):
        framework_defaults = manifest.get("framework_defaults") or {}
        return framework_defaults.get(key, fallback)

    def _inject_global_settings(self, manifest: Dict) -> Dict:
        normalized = deepcopy(manifest)
        normalized["required_credentials"] = validate_required_credentials(normalized.get("required_credentials"))
        settings_schema = dict(normalized.get("settings_schema") or {})

        for legacy_key in (
            "enable_ai_summary",
            "auto_summarize",
            "retention_days",
            "retention_hours",
            "sync_limit",
            "auto_sync",
            "auto_sync_interval",
            "auto_short_summary",
        ):
            settings_schema.pop(legacy_key, None)

        settings_schema["auto_short_summary"] = {
            "type": "boolean",
            "label": "启用 AI 短总结",
            "scope": "system",
            "default": self._get_framework_default(
                normalized,
                "auto_short_summary",
                self._infer_default_auto_short_summary(normalized),
            ),
        }
        settings_schema["retention_hours"] = {
            "type": "integer",
            "label": "数据存活时间(小时)",
            "scope": "system",
            "default": self._get_framework_default(normalized, "retention_hours", 168),
            "description": "-1 为永久保存，默认 7 天",
        }
        settings_schema["sync_limit"] = {
            "type": "integer",
            "label": "同步限制",
            "scope": "system",
            "default": self._get_framework_default(normalized, "sync_limit", 100),
            "description": "每次同步抓取的最大条数",
        }
        settings_schema["auto_sync"] = {
            "type": "boolean",
            "label": "自动同步",
            "scope": "system",
            "default": self._get_framework_default(normalized, "auto_sync", False),
        }
        settings_schema["auto_sync_interval"] = {
            "type": "integer",
            "label": "同步间隔 (分钟)",
            "scope": "system",
            "default": self._get_framework_default(normalized, "auto_sync_interval", 60),
            "description": "自动同步开启后，按此分钟间隔巡检",
        }

        normalized["settings_schema"] = settings_schema
        return normalized

    def register(self, plugin: BasePlugin):
        try:
            manifest = self._inject_global_settings(plugin.manifest)
        except Exception as exc:
            app_log.error(f"Failed to register plugin due to invalid manifest credentials: {exc}")
            return
        plugin_id = manifest.get("id")
        if not plugin_id:
            app_log.error("❌ Failed to register plugin: plugin id is missing.")
            return
        
        plugin._manifest = manifest
        self.plugins[plugin_id] = plugin
        app_log.info(f"🧩 Plugin registered: {manifest.get('name')} ({plugin_id})")

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        return self.plugins.get(plugin_id)

    def get_all_manifests(self) -> List[Dict]:
        return [deepcopy(plugin._manifest or plugin.manifest) for plugin in self.plugins.values()]

    async def ensure_builtin_plugins(self, session) -> None:
        """Ensure built-in plugins are present before any service loads the registry."""
        stmt = insert(PluginRegistryORM).values(
            plugin_id="github_stars",
            name="GitHub Stars",
            module_path="worker.plugins.github.plugin",
            is_enabled=True,
            version="1.0.0",
        )
        stmt = stmt.on_conflict_do_nothing(index_elements=["plugin_id"])
        await session.execute(stmt)
    
    async def load_enabled_plugins(self, session):
        """动态加载已启用的插件"""
        app_log.info("🔌 Loading enabled plugins...")

        await self.ensure_builtin_plugins(session)
        
        # 1. 查询已启用的插件
        result = await session.execute(
            select(PluginRegistryORM).where(PluginRegistryORM.is_enabled == True)
        )
        enabled_plugins = result.scalars().all()
        
        if not enabled_plugins:
            app_log.info("⚠️ No enabled plugins were found.")
            return

        for plugin_record in enabled_plugins:
            try:
                # 2. 动态导入模块
                module_path = plugin_record.module_path
                app_log.info(f"🔍 Loading module: {module_path}")
                module = importlib.import_module(module_path)
                
                # 3. 扫描并实例化 BasePlugin 子类
                found = False
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BasePlugin) and 
                        obj is not BasePlugin):
                        
                        # 实例化插件
                        plugin_instance = obj()
                        
                        # ✨ 核心：Pekno 框架执行依赖注入
                        import json
                        from pathlib import Path
                        
                        # 尝试从模块同级目录读取 manifest.json
                        module_file = getattr(module, '__file__', None)
                        manifest_data = deepcopy(plugin_instance.manifest or {})
                        manifest_data.update({
                            "id": plugin_record.plugin_id,
                            "name": plugin_record.name,
                            "version": plugin_record.version
                        })
                        
                        if module_file:
                            manifest_path = Path(module_file).parent / "manifest.json"
                            if manifest_path.exists():
                                try:
                                    with open(manifest_path, "r", encoding="utf-8") as f:
                                        file_manifest = json.load(f)
                                        # 合并文件配置（文件中的 schema 等更详细）
                                        manifest_data.update(file_manifest)
                                except Exception as e:
                                    app_log.error(f"Failed to read manifest.json: {e}")
                                    
                        plugin_instance._manifest = manifest_data
                        self.register(plugin_instance)
                        found = True
                        break
                
                if not found:
                    app_log.warning(f"⚠️ No matching plugin class was found in module {module_path}")
                    
            except Exception as e:
                app_log.error(f"❌ Failed to load plugin {plugin_record.plugin_id}: {e}")

# 全局单例
plugin_manager = PluginManager()
