from __future__ import annotations

from types import SimpleNamespace

import pytest

from hub.api.mcp.tools.admin import ADMIN_DENIED_MESSAGE, SYSTEM_SCOPE_DENIED_MESSAGE, update_plugin_config


def _make_server(is_admin: bool, scopes: list[str] | None = None):
    return SimpleNamespace(
        request_context=SimpleNamespace(
            request=SimpleNamespace(scope={"state": {"is_admin": is_admin, "scopes": scopes or []}})
        )
    )


@pytest.mark.anyio
async def test_update_plugin_config_denies_non_admin():
    server = _make_server(is_admin=False)

    response = await update_plugin_config(
        server,
        user_id="user-1",
        args={
            "plugin_name": "bilibili",
            "config_json_str": '{"token":"secret"}',
        },
    )

    assert response[0].text == ADMIN_DENIED_MESSAGE


@pytest.mark.anyio
async def test_update_plugin_config_denies_admin_without_system_scope():
    server = _make_server(is_admin=True, scopes=["read:knowledge", "write:star"])

    response = await update_plugin_config(
        server,
        user_id="admin-1",
        args={
            "plugin_name": "bilibili",
            "config_json_str": '{"token":"secret"}',
        },
    )

    assert response[0].text == SYSTEM_SCOPE_DENIED_MESSAGE


@pytest.mark.anyio
async def test_update_plugin_config_updates_plugin_settings_for_admin(monkeypatch):
    server = _make_server(is_admin=True, scopes=["write:system_config"])
    saved_calls: list[tuple[str, str, str, str, str]] = []

    fake_plugin = SimpleNamespace(
        manifest={
            "settings_schema": {
                "token": {"label": "访问令牌"},
                "sync_limit": {"label": "同步数量"},
            }
        }
    )

    from hub.api.mcp.tools import admin as admin_tool_module

    monkeypatch.setattr(admin_tool_module.plugin_manager, "get_plugin", lambda plugin_name: fake_plugin)

    async def fake_set_config(plugin_id: str, key: str, value: str, description: str = "", user_id: str | None = None):
        saved_calls.append((plugin_id, key, value, description, user_id or ""))
        return True

    monkeypatch.setattr(admin_tool_module.ConfigManager, "set_config", staticmethod(fake_set_config))

    response = await update_plugin_config(
        server,
        user_id="admin-1",
        args={
            "plugin_name": "bilibili",
            "config_json_str": '{"token":"cookie","sync_limit":25,"ignored":"x"}',
        },
    )

    assert response[0].text == "Success: 已成功为管理员更新插件 bilibili 的底层配置。"
    assert saved_calls == [
        ("bilibili", "token", "cookie", "访问令牌", "admin-1"),
        ("bilibili", "sync_limit", "25", "同步数量", "admin-1"),
    ]
