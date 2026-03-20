from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Dict, Any, List
import shutil
import os
import json
import tempfile
from datetime import datetime
from pathlib import Path
from shared.plugins.manager import plugin_manager
from shared.config import ConfigManager, SYSTEM_SCOPED_CONFIG_KEYS
from shared.models import ConfigORM, PluginRegistryORM
from shared.database import AsyncSessionLocal
from shared.utils.zip_utils import safe_extract_zip
from worker.plugins.pipeline import reload_system_plugins_task, run_plugin_pipeline_task
from sqlalchemy import select, delete
from hub.core.security import get_current_user, require_admin

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])

# 插件安装相关配置
PLUGIN_INSTALL_DIR = Path("worker/plugins/third_party").resolve()
TEMP_PREVIEW_DIR = Path(tempfile.gettempdir()) / "iris_plugins"

@router.post("/upload_preview")
async def upload_plugin_preview(file: UploadFile = File(...), current_user=Depends(require_admin)):
    """
    步骤1：上传并预检插件
    解压到临时目录，读取 manifest 和源码供审查
    """
    # 确保临时目录存在
    if TEMP_PREVIEW_DIR.exists():
        shutil.rmtree(TEMP_PREVIEW_DIR)
    TEMP_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    
    temp_zip_path = TEMP_PREVIEW_DIR / file.filename
    
    try:
        # 1. 保存 ZIP
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. 安全解压
        # 为每个插件创建一个随机子目录，避免冲突
        import uuid
        extract_dir_name = str(uuid.uuid4())
        extract_path = TEMP_PREVIEW_DIR / extract_dir_name
        extract_path.mkdir()
        
        safe_extract_zip(str(temp_zip_path), str(extract_path))
        
        # 3. 寻找 manifest.json (假设在根目录)
        manifest_path = extract_path / "manifest.json"
        if not manifest_path.exists():
            # 尝试在子目录找（有些压缩包会多一层文件夹）
            subdirs = [d for d in extract_path.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                extract_path = subdirs[0]
                manifest_path = extract_path / "manifest.json"
        
        if not manifest_path.exists():
            raise HTTPException(status_code=400, detail="未找到 manifest.json 描述文件")
            
        # 4. 读取清单 (纯文本解析，不加载代码)
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        # 5. 读取主入口源码 (仅预览)
        # 假设入口文件通常是 plugin.py 或 __init__.py
        source_code = ""
        main_py = extract_path / "plugin.py"
        if not main_py.exists():
            main_py = extract_path / "__init__.py"
            
        if main_py.exists():
            with open(main_py, "r", encoding="utf-8") as f:
                source_code = f.read()
        else:
            source_code = "# 未找到标准入口文件 (plugin.py 或 __init__.py)"
            
        return {
            "temp_token": extract_dir_name, # 用于下一步确认安装
            "manifest": manifest,
            "source_code": source_code,
            "file_structure": [p.name for p in extract_path.iterdir()]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"预检失败: {str(e)}")

@router.post("/confirm_install")
async def confirm_install_plugin(token: str, current_user=Depends(require_admin)):
    """
    步骤2：确认安装
    将临时目录移动到插件目录，写入数据库，触发热重载
    """
    source_path = TEMP_PREVIEW_DIR / token
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="安装会话已过期，请重新上传")
        
    try:
        # 1. 读取 Manifest 获取 ID
        manifest_path = source_path / "manifest.json"
        # 再次检查子目录逻辑
        if not manifest_path.exists():
            subdirs = [d for d in source_path.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                source_path = subdirs[0]
                manifest_path = source_path / "manifest.json"
        
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
            
        plugin_id = manifest.get("id")
        if not plugin_id:
            raise HTTPException(status_code=400, detail="Manifest 缺少插件 ID")
            
        # 2. 移动文件到正式目录
        target_path = PLUGIN_INSTALL_DIR / plugin_id
        if target_path.exists():
            shutil.rmtree(target_path) # 覆盖安装
            
        shutil.move(str(source_path), str(target_path))
        
        # 3. 写入数据库注册表
        module_path = f"worker.plugins.third_party.{plugin_id}.plugin"
        # 尝试猜测入口模块，如果 plugin.py 存在则用 .plugin，否则用包名
        if not (target_path / "plugin.py").exists():
            module_path = f"worker.plugins.third_party.{plugin_id}"

        async with AsyncSessionLocal() as session:
            from sqlalchemy.dialects.postgresql import insert
            stmt = insert(PluginRegistryORM).values(
                plugin_id=plugin_id,
                name=manifest.get("name", "Unknown"),
                module_path=module_path,
                version=manifest.get("version", "1.0.0"),
                is_enabled=True
            ).on_conflict_do_update(
                index_elements=['plugin_id'],
                set_={
                    "name": manifest.get("name"),
                    "module_path": module_path,
                    "version": manifest.get("version"),
                    "is_enabled": True,
                    "installed_at": datetime.now()
                }
            )
            await session.execute(stmt)
            await session.commit()
            
            # 4. 触发双端热重载
            # Hub 端
            await plugin_manager.load_enabled_plugins(session)
            
        # Worker 端
        await reload_system_plugins_task.kiq()
        
        return {"status": "success", "message": f"插件 {plugin_id} 安装成功！"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"安装失败: {str(e)}")

@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str, current_user=Depends(require_admin)):
    """
    卸载插件
    """
    try:
        # 1. 从数据库移除
        async with AsyncSessionLocal() as session:
            # 1.1 删除插件注册记录
            stmt_registry = delete(PluginRegistryORM).where(PluginRegistryORM.plugin_id == plugin_id)
            await session.execute(stmt_registry)
            
            # 1.2 删除插件相关配置 (Fix: 卸载时清理配置)
            stmt_config = delete(ConfigORM).where(ConfigORM.plugin_id == plugin_id)
            await session.execute(stmt_config)
            
            await session.commit()
            
            # 触发 Hub 重载 (从内存移除)
            if plugin_id in plugin_manager.plugins:
                del plugin_manager.plugins[plugin_id]
        
        # 2. 删除物理文件
        plugin_dir = PLUGIN_INSTALL_DIR / plugin_id
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir)
            
        # 3. 触发 Worker 重载
        await reload_system_plugins_task.kiq()
        
        return {"status": "success", "message": f"插件 {plugin_id} 已卸载"}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"卸载失败: {str(e)}")

@router.get("")
async def get_plugins(current_user=Depends(get_current_user)):
    """获取所有插件清单和当前配置"""
    manifests = plugin_manager.get_all_manifests()
    result = []
    
    for manifest in manifests:
        plugin_id = manifest["id"]
        settings_schema = manifest.get("settings_schema", {})
        config_values = {}
        token_preview = None
        secret_configured = False
        
        for key, schema in settings_schema.items():
            val = await ConfigManager.get_config(plugin_id, key, user_id=current_user["id"])
            if val is not None:
                if schema.get("type") == "integer":
                    val = int(val)
                elif schema.get("type") == "boolean":
                    val = (val == "true")
                    
                if schema.get("secret"):
                    secret_configured = True
                    token_preview = f"{val[:4]}..." if len(val) > 4 else val
                    # 不返回真实敏感数据
                    continue
                
                config_values[key] = val
            else:
                config_values[key] = schema.get("default")

        has_secret_field = any(schema.get("secret") for schema in settings_schema.values())
        required_keys = [key for key, schema in settings_schema.items() if schema.get("required")]

        required_configured = True
        for key in required_keys:
            val = await ConfigManager.get_config(plugin_id, key, user_id=current_user["id"])
            if val in (None, ""):
                required_configured = False
                break

        is_configured = secret_configured if has_secret_field else required_configured
        if has_secret_field and required_keys:
            is_configured = secret_configured and required_configured
        
        result.append({
            "manifest": manifest,
            "config": config_values,
            "has_token": is_configured, # 用 is_configured 替代单纯的 has_token
            "token_preview": token_preview
        })
        
    return result

@router.post("/{plugin_id}/config")
async def save_plugin_config(plugin_id: str, config: Dict[str, Any], current_user=Depends(get_current_user)):
    """动态保存插件配置"""
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"找不到插件: {plugin_id}")
        
    settings_schema = plugin.manifest.get("settings_schema", {})
    
    for key, val in config.items():
        if key not in settings_schema:
            continue
            
        schema = settings_schema[key]
        if key in SYSTEM_SCOPED_CONFIG_KEYS and current_user["role"] not in {"admin", "super_admin"}:
            continue
        
        # 针对空值的密码(secret)字段，通常表示不修改
        if schema.get("secret") and (val is None or str(val).strip() == ""):
            continue
            
        str_val = str(val) if not isinstance(val, bool) else ("true" if val else "false")
        
        await ConfigManager.set_config(
            plugin_id, 
            key, 
            str_val, 
            description=schema.get("label", key),
            user_id=current_user["id"],
        )
        
    return {"status": "success", "message": f"{plugin.manifest.get('name')} 配置已保存"}

@router.post("/{plugin_id}/sync")
async def trigger_plugin_sync(plugin_id: str, current_user=Depends(get_current_user)):
    """触发插件同步"""
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"找不到插件: {plugin_id}")
        
    # 异步触发，取代之前的 sync_github_stars_task
    task = await run_plugin_pipeline_task.kiq(plugin_id, None, current_user["id"])
    
    return {
        "status": "accepted",
        "task_id": task.task_id if task else None,
        "message": f"{plugin.manifest.get('name')} 同步任务已加入队列"
    }
