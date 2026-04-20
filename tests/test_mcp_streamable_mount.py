from __future__ import annotations

import json
from types import SimpleNamespace

import anyio
import pytest
from fastapi import FastAPI

from hub.api.mcp import server as mcp_server
from hub.api.mcp.tools import search as mcp_search_tools
from hub.api.middlewares.mcp_auth import MCPAuthMiddleware

VALID_TOKEN = "pekno_pat_test_valid_token"
VALID_UID = "bbf7ad82-19fc-417f-837d-58ec7d869a8e"


def _build_test_app() -> FastAPI:
    test_app = FastAPI()
    test_app.mount("/api/mcp", MCPAuthMiddleware(mcp_server.mcp_app))
    return test_app


def _build_scope(method: str, path: str, headers: dict[str, str] | None = None) -> dict:
    raw_path, _, raw_query = path.partition("?")
    header_items = []
    for key, value in (headers or {}).items():
        header_items.append((key.lower().encode("latin-1"), value.encode("latin-1")))

    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": method.upper(),
        "scheme": "http",
        "path": raw_path,
        "raw_path": raw_path.encode("ascii"),
        "query_string": raw_query.encode("ascii"),
        "headers": header_items,
        "client": ("testclient", 123),
        "server": ("testserver", 80),
        "root_path": "",
    }


async def _invoke_http_app(app, method: str, path: str, headers: dict[str, str] | None = None, body: bytes = b""):
    sent_messages: list[dict] = []
    request_messages = [{"type": "http.request", "body": body, "more_body": False}]
    merged_headers = dict(headers or {})
    if method.upper() == "POST":
        merged_headers.setdefault("Content-Type", "application/json")

    async def receive():
        if request_messages:
            return request_messages.pop(0)
        return {"type": "http.disconnect"}

    async def send(message):
        sent_messages.append(message)

    await app(_build_scope(method, path, merged_headers), receive, send)
    return sent_messages


def _message_status(sent_messages: list[dict]) -> int:
    for message in sent_messages:
        if message["type"] == "http.response.start":
            return int(message["status"])
    raise AssertionError("No http.response.start message was sent.")


def _message_json(sent_messages: list[dict]) -> dict:
    body = b"".join(
        message.get("body", b"")
        for message in sent_messages
        if message["type"] == "http.response.body"
    )
    return json.loads(body.decode("utf-8"))


@pytest.mark.anyio
async def test_mcp_streamable_http_can_initialize_and_call_search(monkeypatch):
    async def fake_hybrid_search(query_text: str, user_id: str, limit: int = 20, source_type: str | None = None):
        return [
            (
                SimpleNamespace(
                    id="item-v2",
                    title="MCP Streamable Result",
                    source_type="article",
                    content_text="Streamable summary",
                    summary="Fallback summary",
                ),
                0.88,
            )
        ]

    monkeypatch.setattr(mcp_search_tools.search_service, "hybrid_search", fake_hybrid_search)

    async def fake_validate_pat(token: str):
        if token != VALID_TOKEN:
            return None
        return {
            "user_id": VALID_UID,
            "username": "Satin",
            "role": "admin",
            "is_admin": True,
            "scopes": ["read:knowledge", "write:star", "write:system_config"],
        }

    monkeypatch.setattr(MCPAuthMiddleware, "_validate_pat", staticmethod(fake_validate_pat))

    app = _build_test_app()
    headers = {
        "Authorization": f"Bearer {VALID_TOKEN}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }

    initialize_messages = await _invoke_http_app(
        app,
        "POST",
        "/api/mcp/v2/stream",
        headers,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-03-26",
                    "capabilities": {},
                    "clientInfo": {"name": "pytest-client", "version": "1.0.0"},
                },
            }
        ).encode("utf-8"),
    )
    assert _message_status(initialize_messages) == 200
    assert _message_json(initialize_messages)["result"]["serverInfo"]["name"] == "pekno"

    initialized_notification_messages = await _invoke_http_app(
        app,
        "POST",
        "/api/mcp/v2/stream",
        headers,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
                "params": {},
            }
        ).encode("utf-8"),
    )
    assert _message_status(initialized_notification_messages) == 202

    tools_messages = await _invoke_http_app(
        app,
        "POST",
        "/api/mcp/v2/stream",
        headers,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/list",
                "params": {},
            }
        ).encode("utf-8"),
    )
    assert _message_status(tools_messages) == 200
    tool_names = [tool["name"] for tool in _message_json(tools_messages)["result"]["tools"]]
    assert "search_knowledge_base" in tool_names

    search_messages = await _invoke_http_app(
        app,
        "POST",
        "/api/mcp/v2/stream",
        headers,
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "search_knowledge_base",
                    "arguments": {"query": "mcp", "limit": 3, "source_type": "article"},
                },
            }
        ).encode("utf-8"),
    )
    assert _message_status(search_messages) == 200
    payload = json.loads(_message_json(search_messages)["result"]["content"][0]["text"])
    assert payload == [
        {
            "id": "item-v2",
            "title": "MCP Streamable Result",
            "source_type": "article",
            "summary": "Streamable summary",
        }
    ]
