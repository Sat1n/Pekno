from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from urllib.parse import unquote

import anyio
import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

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


class _SSEConnection:
    def __init__(self):
        self.sent_messages: list[dict] = []
        self.endpoint_ready = anyio.Event()
        self.tool_response_ready = anyio.Event()
        self.endpoint_uri: str | None = None
        self._send_stream = None
        self._stream_buffer = ""

    async def send(self, message):
        self.sent_messages.append(message)
        if message["type"] != "http.response.body":
            return
        chunk = message.get("body", b"").decode("utf-8", errors="ignore")
        self._stream_buffer += chunk
        if "event: endpoint" not in chunk:
            if '"id":2' in self._stream_buffer:
                self.tool_response_ready.set()
            return
        event_name = None
        data_lines: list[str] = []
        for line in self._stream_buffer.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if event_name == "endpoint" and data_lines and self.endpoint_uri is None:
            self.endpoint_uri = unquote("\n".join(data_lines))
            self.endpoint_ready.set()
        if '"id":2' in self._stream_buffer:
            self.tool_response_ready.set()

    async def disconnect(self):
        if self._send_stream is not None:
            await self._send_stream.send({"type": "http.disconnect"})


async def _open_sse_connection(app, headers: dict[str, str]):
    connection = _SSEConnection()
    send_stream, receive_stream = anyio.create_memory_object_stream(10)
    connection._send_stream = send_stream
    await send_stream.send({"type": "http.request", "body": b"", "more_body": False})

    async def receive():
        return await receive_stream.receive()

    return connection, send_stream, receive, connection.send


def _message_status(sent_messages: list[dict]) -> int:
    for message in sent_messages:
        if message["type"] == "http.response.start":
            return int(message["status"])
    raise AssertionError("No http.response.start message was sent.")


def _parse_sse_events(stream_text: str) -> list[tuple[str | None, str]]:
    events: list[tuple[str | None, str]] = []
    for block in stream_text.split("\r\n\r\n"):
        block = block.strip()
        if not block:
            continue
        event_name: str | None = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event:"):
                event_name = line.split(":", 1)[1].strip()
            elif line.startswith("data:"):
                data_lines.append(line.split(":", 1)[1].strip())
        if event_name or data_lines:
            events.append((event_name, "\n".join(data_lines)))
    return events


def test_mcp_sse_rejects_invalid_token():
    with TestClient(_build_test_app()) as client:
        response = client.get("/api/mcp/sse", headers={"Authorization": "Bearer invalid-token"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Invalid token"


@pytest.mark.anyio
async def test_mcp_sse_valid_token_can_call_search_tool_and_disconnect_cleanly(monkeypatch, caplog):
    search_calls: list[dict] = []

    async def fake_hybrid_search(query_text: str, user_id: str, limit: int = 20, source_type: str | None = None):
        search_calls.append(
            {
                "query_text": query_text,
                "user_id": user_id,
                "limit": limit,
                "source_type": source_type,
            }
        )
        return [
            (
                SimpleNamespace(
                    id="item-1",
                    title="MCP Search Result",
                    source_type="article",
                    content_text="This is the indexed summary.",
                    summary="Fallback summary",
                ),
                0.99,
            )
        ]

    monkeypatch.setattr(mcp_search_tools.search_service, "hybrid_search", fake_hybrid_search)

    async def fake_validate_pat(token: str):
        if token != VALID_TOKEN:
            return None
        return {
            "user_id": VALID_UID,
            "username": "Satin",
            "role": "super_admin",
            "is_admin": True,
            "scopes": ["read:knowledge", "write:star"],
        }

    monkeypatch.setattr(MCPAuthMiddleware, "_validate_pat", staticmethod(fake_validate_pat))
    caplog.set_level(logging.INFO)

    mounted_app = _build_test_app()
    headers = {"Authorization": f"Bearer {VALID_TOKEN}"}

    connection, send_stream, receive, send = await _open_sse_connection(mounted_app, headers)

    async with anyio.create_task_group() as tg:
        tg.start_soon(mounted_app, _build_scope("GET", "/api/mcp/sse", headers), receive, send)
        with anyio.fail_after(5):
            await connection.endpoint_ready.wait()

        assert connection.endpoint_uri is not None
        assert connection.endpoint_uri.startswith("/api/mcp/messages?session_id=")

        initialize_messages = await _invoke_http_app(
            mounted_app,
            "POST",
            connection.endpoint_uri,
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
        assert _message_status(initialize_messages) == 202

        initialized_notification_messages = await _invoke_http_app(
            mounted_app,
            "POST",
            connection.endpoint_uri,
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

        tool_call_messages = await _invoke_http_app(
            mounted_app,
            "POST",
            connection.endpoint_uri,
            headers,
            json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "search_knowledge_base",
                        "arguments": {"query": "mcp", "limit": 3, "source_type": "article"},
                    },
                }
            ).encode("utf-8"),
        )
        assert _message_status(tool_call_messages) == 202

        with anyio.fail_after(5):
            await connection.tool_response_ready.wait()

        await connection.disconnect()
        tg.cancel_scope.cancel()

    message_chunks = [
        message.get("body", b"").decode("utf-8", errors="ignore")
        for message in connection.sent_messages
        if message["type"] == "http.response.body" and message.get("body")
    ]
    combined_stream = "\n".join(message_chunks)
    events = _parse_sse_events(combined_stream)
    assert any(event_name == "endpoint" for event_name, _ in events)

    message_payloads = [
        json.loads(event_data)
        for event_name, event_data in events
        if event_name == "message"
    ]
    initialize_payload = next(payload for payload in message_payloads if payload.get("id") == 1)
    tool_payload_message = next(payload for payload in message_payloads if payload.get("id") == 2)

    assert initialize_payload["result"]["serverInfo"]["name"] == "iris-hub"

    tool_payload = json.loads(tool_payload_message["result"]["content"][0]["text"])
    assert tool_payload == [
        {
            "id": "item-1",
            "title": "MCP Search Result",
            "source_type": "article",
            "summary": "This is the indexed summary.",
        }
    ]

    assert search_calls == [
        {
            "query_text": "mcp",
            "user_id": VALID_UID,
            "limit": 3,
            "source_type": "article",
        }
    ]
    assert "NoneType" not in caplog.text
    assert "Unexpected ASGI message" not in caplog.text
