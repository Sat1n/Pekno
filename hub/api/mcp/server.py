from __future__ import annotations

import asyncio
import logging

from anyio import ClosedResourceError
from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.server.streamable_http import StreamableHTTPServerTransport
from mcp.types import TextContent
from starlette.requests import Request

from hub.api.mcp.context import get_user_id
from hub.api.mcp.tools import TOOL_DEFINITIONS, TOOL_HANDLERS

logger = logging.getLogger("iris-mcp")
sse_transport = SseServerTransport("/messages")
server = Server("iris-hub")


@server.list_tools()
async def handle_list_tools():
    return TOOL_DEFINITIONS


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict):
    user_id = get_user_id(server)

    if not user_id:
        return [TextContent(type="text", text="Error: Missing authenticated MCP request context.")]

    handler = TOOL_HANDLERS.get(name)
    if not handler:
        return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]

    return await handler(server, user_id, arguments or {})


async def handle_sse(request: Request):
    scope_state = request.scope.get("state", {}) or {}
    logger.info(
        "MCP SSE session opened for user=%s role=%s is_admin=%s",
        scope_state.get("user_id"),
        scope_state.get("role"),
        scope_state.get("is_admin"),
    )
    async with sse_transport.connect_sse(request.scope, request.receive, request._send) as (
        read_s,
        write_s,
    ):
        await server.run(read_s, write_s, server.create_initialization_options())
    logger.info("MCP SSE session closed cleanly for user=%s", scope_state.get("username"))


async def handle_messages(request: Request):
    try:
        await sse_transport.handle_post_message(request.scope, request.receive, request._send)
    except ClosedResourceError:
        logger.info("MCP message dropped because the SSE session was already closed.")


async def _send_status(send, status: int, body: str) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"text/plain; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": body.encode("utf-8")})


class MCPServerApp:
    def __init__(self) -> None:
        self._streamable_http_transport: StreamableHTTPServerTransport | None = None
        self._streamable_connect_cm = None
        self._streamable_server_task: asyncio.Task | None = None
        self._streamable_lock = asyncio.Lock()

    async def _ensure_streamable_ready(self) -> None:
        transport = self._streamable_http_transport
        server_task = self._streamable_server_task
        if transport is not None and server_task is not None and not server_task.done():
            return

        async with self._streamable_lock:
            transport = self._streamable_http_transport
            server_task = self._streamable_server_task
            if transport is not None and server_task is not None and not server_task.done():
                return

            transport = StreamableHTTPServerTransport(
                mcp_session_id=None,
                is_json_response_enabled=True,
            )
            connect_cm = transport.connect()
            read_stream, write_stream = await connect_cm.__aenter__()

            self._streamable_http_transport = transport
            self._streamable_connect_cm = connect_cm
            self._streamable_server_task = asyncio.create_task(
                server.run(
                    read_stream,
                    write_stream,
                    server.create_initialization_options(),
                )
            )

    async def handle_streamable_http(self, scope, receive, send) -> None:
        await self._ensure_streamable_ready()
        transport = self._streamable_http_transport
        if transport is None:
            await _send_status(send, 500, "Streamable HTTP transport is unavailable")
            return
        await transport.handle_request(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await _send_status(send, 404, "Not found")
            return

        path = (scope.get("path", "") or "/").rstrip("/") or "/"
        method = scope.get("method", "GET").upper()

        if path.endswith("/sse") and method == "GET":
            request = Request(scope, receive, send)
            await handle_sse(request)
            return

        if path.endswith("/messages") and method == "POST":
            request = Request(scope, receive, send)
            await handle_messages(request)
            return

        if path.endswith("/v2/stream") and method in {"GET", "POST", "DELETE"}:
            await self.handle_streamable_http(scope, receive, send)
            return

        await _send_status(send, 404, "Not found")


mcp_app = MCPServerApp()
