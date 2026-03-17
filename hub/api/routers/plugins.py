from fastapi import APIRouter, HTTPException
from typing import Dict, Any, List
from shared.plugins.manager import plugin_manager
from shared.config import ConfigManager
from worker.plugins.pipeline import run_plugin_pipeline_task

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])

@router.get("")
async def get_plugins():
    """获取所有插件清单和当前配置"""
    manifests = plugin_manager.get_all_manifests()
    result = []
    
    for manifest in manifests:
        plugin_id = manifest["id"]
        settings_schema = manifest.get("settings_schema", {})
        config_values = {}
        has_token = False
        token_preview = None
        
        for key, schema in settings_schema.items():
            val = await ConfigManager.get_config(plugin_id, key)
            if val is not None:
                if schema.get("type") == "integer":
                    val = int(val)
                elif schema.get("type") == "boolean":
                    val = (val == "true")
                    
                if schema.get("secret"):
                    has_token = True
                    token_preview = val[:4] + "****" if len(val) > 4 else None
                    # 不返回真实敏感数据
                    continue
                else:
                    config_values[key] = val
            else:
                config_values[key] = schema.get("default")
                if schema.get("secret"):
                    has_token = False
                
        result.append({
            "manifest": manifest,
            "config": config_values,
            "has_token": has_token,
            "token_preview": token_preview
        })
        
    return result

@router.post("/{plugin_id}/config")
async def save_plugin_config(plugin_id: str, config: Dict[str, Any]):
    """动态保存插件配置"""
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"找不到插件: {plugin_id}")
        
    settings_schema = plugin.manifest.get("settings_schema", {})
    
    for key, val in config.items():
        if key not in settings_schema:
            continue
            
        schema = settings_schema[key]
        
        # 针对空值的密码(secret)字段，通常表示不修改
        if schema.get("secret") and (val is None or str(val).strip() == ""):
            continue
            
        str_val = str(val) if not isinstance(val, bool) else ("true" if val else "false")
        
        await ConfigManager.set_config(
            plugin_id, 
            key, 
            str_val, 
            description=schema.get("label", key)
        )
        
    return {"status": "success", "message": f"{plugin.manifest.get('name')} 配置已保存"}

@router.post("/{plugin_id}/sync")
async def trigger_plugin_sync(plugin_id: str):
    """触发插件同步"""
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"找不到插件: {plugin_id}")
        
    # 异步触发，取代之前的 sync_github_stars_task
    task = await run_plugin_pipeline_task.kiq(plugin_id)
    
    return {
        "status": "accepted",
        "task_id": task.task_id if task else None,
        "message": f"{plugin.manifest.get('name')} 同步任务已加入队列"
    }
