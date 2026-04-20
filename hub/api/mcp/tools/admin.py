from __future__ import annotations

import json
import logging

from mcp.types import TextContent, Tool

from hub.api.mcp.context import get_is_admin, get_scopes
from shared.config import ConfigManager
from shared.plugins.manager import plugin_manager

logger = logging.getLogger("Pekno-mcp")

ADMIN_DENIED_MESSAGE = (
    "Permission Denied: [⚠️ 严重警告] 您正在尝试越权操作。"
    "此工具仅限超级管理员 Agent 极其慎重地使用。您的操作已被记录。"
)
SYSTEM_SCOPE_DENIED_MESSAGE = (
    "Permission Denied: 您的 Token 缺少 write:system_config 权限，"
    "无法执行底层系统配置修改。"
)

UPDATE_PLUGIN_CONFIG_TOOL = Tool(
    name="update_plugin_config",
    description="Admin-only tool. Update the underlying plugin configuration for a specific plugin using a JSON payload.",
    inputSchema={
        "type": "object",
        "properties": {
            "plugin_name": {"type": "string", "description": "Plugin ID, such as bilibili or github_stars"},
            "config_json_str": {
                "type": "string",
                "description": "Plugin config JSON string, e.g. a JSON object containing cookie, token, or API keys.",
            },
        },
        "required": ["plugin_name", "config_json_str"],
    },
)


async def update_plugin_config(server, user_id: str, args: dict):
    if not get_is_admin(server):
        logger.warning(
            "Blocked unauthorized MCP admin tool attempt: tool=update_plugin_config user_id=%s",
            user_id,
        )
        return [TextContent(type="text", text=ADMIN_DENIED_MESSAGE)]

    scopes = get_scopes(server)
    if "write:system_config" not in scopes:
        logger.warning(
            "Blocked MCP admin tool without scope: tool=update_plugin_config user_id=%s scopes=%s",
            user_id,
            scopes,
        )
        return [TextContent(type="text", text=SYSTEM_SCOPE_DENIED_MESSAGE)]

    plugin_name = str(args.get("plugin_name", "")).strip()
    config_json_str = str(args.get("config_json_str", "")).strip()
    if not plugin_name or not config_json_str:
        return [TextContent(type="text", text="Error: plugin_name and config_json_str are required.")]

    plugin = plugin_manager.get_plugin(plugin_name)
    if not plugin:
        return [TextContent(type="text", text=f"Error: 找不到插件 {plugin_name}")]

    try:
        config_data = json.loads(config_json_str)
    except json.JSONDecodeError as exc:
        return [TextContent(type="text", text=f"Error: config_json_str 不是合法 JSON: {exc}")]

    if not isinstance(config_data, dict):
        return [TextContent(type="text", text="Error: config_json_str 必须是 JSON 对象。")]

    settings_schema = plugin.manifest.get("settings_schema", {})
    updated_keys: list[str] = []

    for key, value in config_data.items():
        if key not in settings_schema:
            continue

        schema = settings_schema[key]
        serialized_value = str(value) if not isinstance(value, bool) else ("true" if value else "false")
        success = await ConfigManager.set_config(
            plugin_name,
            key,
            serialized_value,
            description=schema.get("label", key),
            user_id=user_id,
        )
        if not success:
            return [TextContent(type="text", text=f"Error: 保存插件配置失败: {plugin_name}.{key}")]
        updated_keys.append(key)

    if not updated_keys:
        return [
            TextContent(
                type="text",
                text=f"Error: 未找到可写入的配置项。请确认插件 {plugin_name} 存在且 JSON key 与 settings_schema 匹配。",
            )
        ]

    logger.info(
        "MCP admin config updated: plugin=%s user_id=%s keys=%s",
        plugin_name,
        user_id,
        ",".join(updated_keys),
    )
    return [TextContent(type="text", text=f"Success: 已成功为管理员更新插件 {plugin_name} 的底层配置。")]
