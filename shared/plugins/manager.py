from typing import Dict, List, Optional
import importlib
import inspect
from sqlalchemy import select
from shared.plugins.base import BasePlugin
from shared.logger import hub_log
from shared.models import PluginRegistryORM

class PluginManager:
    """插件管理器 (单例)"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(PluginManager, cls).__new__(cls)
            cls._instance.plugins = {}
        return cls._instance

    def register(self, plugin: BasePlugin):
        manifest = plugin.manifest
        plugin_id = manifest.get("id")
        if not plugin_id:
            hub_log.error("❌ 无法注册插件：未找到 plugin id")
            return
            
        self.plugins[plugin_id] = plugin
        hub_log.info(f"🧩 插件已注册: {manifest.get('name')} ({plugin_id})")

    def get_plugin(self, plugin_id: str) -> Optional[BasePlugin]:
        return self.plugins.get(plugin_id)

    def get_all_manifests(self) -> List[Dict]:
        return [plugin.manifest for plugin in self.plugins.values()]
    
    async def load_enabled_plugins(self, session):
        """动态加载已启用的插件"""
        hub_log.info("🔌 开始加载已启用的插件...")
        
        # 1. 查询已启用的插件
        result = await session.execute(
            select(PluginRegistryORM).where(PluginRegistryORM.is_enabled == True)
        )
        enabled_plugins = result.scalars().all()
        
        if not enabled_plugins:
            hub_log.info("⚠️ 没有找到已启用的插件")
            return

        for plugin_record in enabled_plugins:
            try:
                # 2. 动态导入模块
                module_path = plugin_record.module_path
                hub_log.info(f"🔍 正在加载模块: {module_path}")
                module = importlib.import_module(module_path)
                
                # 3. 扫描并实例化 BasePlugin 子类
                found = False
                for name, obj in inspect.getmembers(module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BasePlugin) and 
                        obj is not BasePlugin):
                        
                        # 实例化插件
                        plugin_instance = obj()
                        
                        # ✨ 核心：Iris 框架执行依赖注入
                        import json
                        from pathlib import Path
                        
                        # 尝试从模块同级目录读取 manifest.json
                        module_file = getattr(module, '__file__', None)
                        manifest_data = {
                            "id": plugin_record.plugin_id,
                            "name": plugin_record.name,
                            "version": plugin_record.version
                        }
                        
                        if module_file:
                            manifest_path = Path(module_file).parent / "manifest.json"
                            if manifest_path.exists():
                                try:
                                    with open(manifest_path, "r", encoding="utf-8") as f:
                                        file_manifest = json.load(f)
                                        # 合并文件配置（文件中的 schema 等更详细）
                                        manifest_data.update(file_manifest)
                                except Exception as e:
                                    hub_log.error(f"读取 manifest.json 失败: {e}")
                                    
                        plugin_instance._manifest = manifest_data
                        
                        self.register(plugin_instance)
                        found = True
                        break
                
                if not found:
                    hub_log.warning(f"⚠️ 在模块 {module_path} 中未找到匹配的插件类")
                    
            except Exception as e:
                hub_log.error(f"❌ 加载插件 {plugin_record.plugin_id} 失败: {e}")

# 全局单例
plugin_manager = PluginManager()
