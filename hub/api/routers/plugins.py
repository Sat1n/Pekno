from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import Dict, Any, List
import shutil
import os
import json
import tempfile
from datetime import datetime
from pathlib import Path
from shared.plugins.manager import plugin_manager
from shared.config import ConfigManager, SYSTEM_SCOPED_CONFIG_KEYS, ConfigKeys
from shared.constants import PLATFORM_WHITELIST
from shared.credentials import get_user_credential, mask_credential, validate_required_credentials, upsert_user_credential, _is_cookie_file_platform, get_cookie_file_path, validate_cookie_file
from shared.models import ConfigORM, PluginRegistryORM
from shared.database import AsyncSessionLocal
from shared.utils.zip_utils import safe_extract_zip
from worker.plugins.pipeline import reload_system_plugins_task, run_plugin_pipeline_task
from sqlalchemy import select, delete
from hub.core.security import get_current_user, require_admin
from shared.api_errors import ApiError
from shared.utils.path_guard import safe_resolve_path

router = APIRouter(prefix="/api/plugins", tags=["Plugins"])

# Plugin installation paths
PLUGIN_INSTALL_DIR = Path("worker/plugins/third_party").resolve()
TEMP_PREVIEW_DIR = Path(tempfile.gettempdir()) / "pekno_plugins"


def _ensure_plugin_install_dir() -> None:
    PLUGIN_INSTALL_DIR.mkdir(parents=True, exist_ok=True)
    init_file = PLUGIN_INSTALL_DIR / "__init__.py"
    if not init_file.exists():
        init_file.write_text("", encoding="utf-8")


async def _get_bound_credentials(plugin_id: str, user_id: str, required_credentials: list[str]) -> list[str]:
    bound: list[str] = []
    for platform in required_credentials:
        is_bound = await ConfigManager.get_config(
            plugin_id,
            ConfigKeys.credential_binding(platform),
            user_id=user_id,
        )
        if is_bound == "true":
            bound.append(platform)
    return bound


async def _resolve_plugin_credential_state(
    plugin_id: str,
    user_id: str,
    manifest: dict[str, Any],
    settings_schema: dict[str, Any],
) -> dict[str, Any]:
    required_credentials = validate_required_credentials(manifest.get("required_credentials"))
    bound_credentials = await _get_bound_credentials(plugin_id, user_id, required_credentials)

    token_preview = None
    secret_configured = False
    config_values: dict[str, Any] = {}

    for key, schema in settings_schema.items():
        val = await ConfigManager.get_config(plugin_id, key, user_id=user_id)
        if val is not None:
            if schema.get("type") == "integer":
                val = int(val)
            elif schema.get("type") == "boolean":
                val = (val == "true")
            if schema.get("secret"):
                secret_configured = True
                token_preview = f"{val[:4]}..." if len(val) > 4 else val
                continue
            config_values[key] = val
        else:
            config_values[key] = schema.get("default")

    credential_states: list[dict[str, Any]] = []
    has_required_credentials = True
    for platform in required_credentials:
        if _is_cookie_file_platform(platform):
            cookie_path = get_cookie_file_path(user_id, platform)
            cookie_validation = validate_cookie_file(platform, cookie_path)
            is_bound = platform in bound_credentials
            file_exists = cookie_validation.get("file_exists", False)
            is_valid = cookie_validation.get("valid", False)
            status = "missing"
            if is_bound and file_exists:
                status = "applied"
            elif file_exists:
                status = "available"
            if not is_valid:
                has_required_credentials = False
            elif not is_bound and file_exists:
                has_required_credentials = False
            credential_states.append(
                {
                    "platform": platform,
                    "label": PLATFORM_WHITELIST[platform]["label"],
                    "status": status,
                    "is_bound": is_bound,
                    "has_global": file_exists,
                    "credential_kind": "cookie_file",
                    "cookie_file_date": cookie_validation.get("file_date"),
                    "cookie_valid": is_valid,
                    "found_keys": cookie_validation.get("found_keys", []),
                    "missing_keys": cookie_validation.get("missing_keys", []),
                    "required_keys": list(PLATFORM_WHITELIST[platform].get("required_cookie_keys", [])),
                }
            )
            continue

        global_credential = await get_user_credential(user_id, platform)
        has_global = global_credential is not None
        is_bound = platform in bound_credentials
        status = "missing"
        masked_value = mask_credential(global_credential.token_value) if global_credential else None
        if is_bound and has_global:
            status = "applied"
        elif has_global:
            status = "available"
            has_required_credentials = False
        else:
            has_required_credentials = False
        credential_states.append(
            {
                "platform": platform,
                "label": PLATFORM_WHITELIST[platform]["label"],
                "status": status,
                "masked_value": masked_value,
                "is_bound": is_bound,
                "has_global": has_global,
            }
        )

    required_keys = [key for key, schema in settings_schema.items() if schema.get("required")]
    required_configured = True
    for key in required_keys:
        val = await ConfigManager.get_config(plugin_id, key, user_id=user_id)
        if val in (None, ""):
            required_configured = False
            break

    has_secret_field = any(schema.get("secret") for schema in settings_schema.values())
    if has_secret_field and required_keys:
        base_configured = secret_configured and required_configured
    elif has_secret_field:
        base_configured = secret_configured
    elif required_keys:
        base_configured = required_configured
    else:
        base_configured = True
    if required_credentials:
        is_configured = (base_configured and has_required_credentials) if (has_secret_field or required_keys) else has_required_credentials
        if not token_preview:
            first_applied = next((state for state in credential_states if state["status"] == "applied"), None)
            if first_applied:
                token_preview = first_applied["masked_value"]
    else:
        is_configured = base_configured

    return {
        "config_values": config_values,
        "token_preview": token_preview,
        "is_configured": is_configured,
        "credential_bindings": bound_credentials,
        "credential_states": credential_states,
    }

@router.post("/upload_preview")
async def upload_plugin_preview(file: UploadFile = File(...), current_user=Depends(require_admin)):
    """
    Step 1: Upload and preview a plugin package before installation.
    """
    # Ensure the temporary preview directory exists
    if TEMP_PREVIEW_DIR.exists():
        shutil.rmtree(TEMP_PREVIEW_DIR)
    TEMP_PREVIEW_DIR.mkdir(parents=True, exist_ok=True)
    
    # Sanitize filename to prevent directory traversal
    safe_filename = Path(file.filename or "plugin.zip").name
    temp_zip_path = safe_resolve_path(TEMP_PREVIEW_DIR, safe_filename)
    
    try:
        # 1. Persist ZIP
        with open(temp_zip_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # 2. Extract safely into an isolated directory
        import uuid
        extract_dir_name = str(uuid.uuid4())
        extract_path = TEMP_PREVIEW_DIR / extract_dir_name
        extract_path.mkdir()
        
        safe_extract_zip(str(temp_zip_path), str(extract_path))
        
        # 3. Find manifest.json
        manifest_path = extract_path / "manifest.json"
        if not manifest_path.exists():
            # Some archives wrap plugin files inside an extra root directory
            subdirs = [d for d in extract_path.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                extract_path = subdirs[0]
                manifest_path = extract_path / "manifest.json"

        if not manifest_path.exists():
            raise HTTPException(status_code=400, detail="manifest.json was not found in the uploaded plugin package.")

        # 4. Read manifest as plain text only, without importing plugin code
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["required_credentials"] = validate_required_credentials(manifest.get("required_credentials"))

        # 5. Read the main entry source for preview only
        source_code = ""
        main_py = extract_path / "plugin.py"
        if not main_py.exists():
            main_py = extract_path / "__init__.py"
            
        if main_py.exists():
            with open(main_py, "r", encoding="utf-8") as f:
                source_code = f.read()
        else:
            source_code = "# No standard entry file was found (plugin.py or __init__.py)"
            
        return {
            "temp_token": extract_dir_name, # 用于下一步确认安装
            "manifest": manifest,
            "source_code": source_code,
            "file_structure": [p.name for p in extract_path.iterdir()]
        }
        
    except ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plugin preview failed: {str(e)}")

@router.post("/confirm_install")
async def confirm_install_plugin(token: str, current_user=Depends(require_admin)):
    """
    Step 2: Confirm installation, move files into place, persist registry state,
    and trigger hot reload on runtime services.
    """
    # Sanitize token to prevent directory traversal
    safe_token = Path(token).name
    source_path = TEMP_PREVIEW_DIR / safe_token
    if not source_path.exists():
        raise HTTPException(status_code=404, detail="The installation session expired. Please upload the plugin again.")
        
    try:
        _ensure_plugin_install_dir()

        # 1. Read manifest to get plugin id
        manifest_path = source_path / "manifest.json"
        # Re-check nested root directory layout
        if not manifest_path.exists():
            subdirs = [d for d in source_path.iterdir() if d.is_dir()]
            if len(subdirs) == 1:
                source_path = subdirs[0]
                manifest_path = source_path / "manifest.json"
        
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        manifest["required_credentials"] = validate_required_credentials(manifest.get("required_credentials"))

        plugin_id = manifest.get("id")
        if not plugin_id:
            raise HTTPException(status_code=400, detail="The plugin manifest is missing an id field.")

        # 2. Move files into the installed plugin directory
        target_path = PLUGIN_INSTALL_DIR / plugin_id
        if target_path.exists():
            shutil.rmtree(target_path)
            
        shutil.move(str(source_path), str(target_path))
        
        # 3. Persist plugin registry entry
        module_path = f"worker.plugins.third_party.{plugin_id}.plugin"
        # If plugin.py is missing, fall back to the package root module
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
            
            # 4. Trigger hot reload for Hub
            await plugin_manager.load_enabled_plugins(session)

        # Worker side
        await reload_system_plugins_task.kiq()

        return {"status": "success", "message": f"Plugin {plugin_id} was installed successfully."}

    except ApiError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plugin installation failed: {str(e)}")

@router.delete("/{plugin_id}")
async def uninstall_plugin(plugin_id: str, current_user=Depends(require_admin)):
    """Uninstall a plugin."""
    try:
        async with AsyncSessionLocal() as session:
            existing = await session.execute(
                select(PluginRegistryORM.plugin_id).where(PluginRegistryORM.plugin_id == plugin_id)
            )
            exists_in_registry = existing.scalar_one_or_none() is not None

        plugin_dir = PLUGIN_INSTALL_DIR / plugin_id
        if not exists_in_registry and not plugin_dir.exists():
            raise HTTPException(status_code=404, detail=f"Plugin was not found: {plugin_id}")

        # 1. Remove plugin metadata from the database
        async with AsyncSessionLocal() as session:
            # Remove registry row
            stmt_registry = delete(PluginRegistryORM).where(PluginRegistryORM.plugin_id == plugin_id)
            await session.execute(stmt_registry)

            # Remove plugin-related configuration
            stmt_config = delete(ConfigORM).where(ConfigORM.plugin_id == plugin_id)
            await session.execute(stmt_config)

            await session.commit()

            # Remove it from Hub in-memory registry
            if plugin_id in plugin_manager.plugins:
                del plugin_manager.plugins[plugin_id]

        # 2. Remove files
        if plugin_dir.exists():
            shutil.rmtree(plugin_dir, ignore_errors=True)

        # 3. Trigger worker reload
        await reload_system_plugins_task.kiq()

        return {"status": "success", "message": f"Plugin {plugin_id} was uninstalled."}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Plugin uninstall failed: {str(e)}")

@router.get("/active")
async def get_active_plugins(current_user=Depends(get_current_user)):
    """Return active plugins configured for the current user."""
    manifests = plugin_manager.get_all_manifests()
    result = []
    
    for manifest in manifests:
        plugin_id = manifest["id"]
        source_type = manifest.get("source_type", plugin_id)
        settings_schema = manifest.get("settings_schema", {})
        plugin_state = await _resolve_plugin_credential_state(plugin_id, current_user["id"], manifest, settings_schema)

        if plugin_state["is_configured"]:
            result.append({
                "id": plugin_id,
                "name": manifest.get("name", plugin_id),
                "source_type": source_type
            })
            
    return result

@router.get("")
async def get_plugins(current_user=Depends(get_current_user)):
    """Return all plugin manifests with the current user's resolved configuration state."""
    manifests = plugin_manager.get_all_manifests()
    result = []
    
    for manifest in manifests:
        plugin_id = manifest["id"]
        settings_schema = manifest.get("settings_schema", {})
        plugin_state = await _resolve_plugin_credential_state(plugin_id, current_user["id"], manifest, settings_schema)
        
        result.append({
            "manifest": manifest,
            "config": plugin_state["config_values"],
            "has_token": plugin_state["is_configured"],
            "token_preview": plugin_state["token_preview"],
            "credential_bindings": plugin_state["credential_bindings"],
            "credential_states": plugin_state["credential_states"],
        })
        
    return result

@router.post("/{plugin_id}/config")
async def save_plugin_config(plugin_id: str, config: Dict[str, Any], current_user=Depends(get_current_user)):
    """Save plugin configuration and optional global credential bindings."""
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin was not found: {plugin_id}")
        
    settings_schema = plugin.manifest.get("settings_schema", {})
    required_credentials = validate_required_credentials(plugin.manifest.get("required_credentials"))

    apply_global_credentials = {
        platform
        for platform in config.pop("__apply_global_credentials", []) or []
        if platform in required_credentials
    }
    global_credential_values = dict(config.pop("__global_credentials", {}) or {})

    for platform in required_credentials:
        entered_value = str(global_credential_values.get(platform, "") or "").strip()
        if entered_value:
            await upsert_user_credential(current_user["id"], platform, entered_value)
            success = await ConfigManager.set_config(
                plugin_id,
                ConfigKeys.credential_binding(platform),
                "true",
                description=f"Credential binding for {platform}",
                user_id=current_user["id"],
            )
            if not success:
                raise HTTPException(status_code=500, detail=f"Failed to save credential binding: {platform}")
        elif platform in apply_global_credentials:
            credential = await get_user_credential(current_user["id"], platform)
            if not credential:
                raise HTTPException(status_code=400, detail=f"Global credential is not available for platform: {platform}")
            success = await ConfigManager.set_config(
                plugin_id,
                ConfigKeys.credential_binding(platform),
                "true",
                description=f"Credential binding for {platform}",
                user_id=current_user["id"],
            )
            if not success:
                raise HTTPException(status_code=500, detail=f"Failed to save credential binding: {platform}")

    for key, val in config.items():
        if key not in settings_schema:
            continue
            
        schema = settings_schema[key]
        if key in SYSTEM_SCOPED_CONFIG_KEYS and current_user["role"] not in {"admin", "super_admin"}:
            continue
        
        # Empty secret input usually means "leave unchanged"
        if schema.get("secret") and (val is None or str(val).strip() == ""):
            continue
            
        str_val = str(val) if not isinstance(val, bool) else ("true" if val else "false")
        
        success = await ConfigManager.set_config(
            plugin_id,
            key,
            str_val,
            description=schema.get("label", key),
            user_id=current_user["id"],
        )
        if not success:
            raise HTTPException(status_code=500, detail=f"Failed to save plugin setting: {key}")

    return {"status": "success", "message": f"{plugin.manifest.get('name')} configuration was saved."}

@router.post("/{plugin_id}/sync")
async def trigger_plugin_sync(plugin_id: str, current_user=Depends(get_current_user)):
    """Trigger a manual sync for a plugin."""
    plugin = plugin_manager.get_plugin(plugin_id)
    if not plugin:
        raise HTTPException(status_code=404, detail=f"Plugin was not found: {plugin_id}")
        
    # 异步触发，取代之前的 sync_github_stars_task
    task = await run_plugin_pipeline_task.kiq(plugin_id, None, current_user["id"])
    
    return {
        "status": "accepted",
        "task_id": task.task_id if task else None,
        "message": f"{plugin.manifest.get('name')} sync task has been queued."
    }
