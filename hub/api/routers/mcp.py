"""
Iris Hub MCP Server — SSE Transport with per-user JWT Identity Isolation.
Uses the low-level mcp.server API compatible with mcp SDK v1.26+.

NOTE: After an SSE session disconnects, uvicorn may log a harmless
"RuntimeError: Unexpected ASGI message 'http.response.start'" because
Starlette's endpoint wrapper tries to send the returned Response() after
connect_sse already completed the HTTP lifecycle. This does NOT affect
functionality — all MCP operations complete successfully before this fires.
"""
import json
import logging
from datetime import timedelta

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from mcp.server.lowlevel import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent

from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from hub.core.security import SECRET_KEY, ALGORITHM
from shared.time_utils import now_in_app_timezone_naive
from sqlalchemy import select, and_, desc

from jose import jwt as jose_jwt

logger = logging.getLogger("iris-mcp")

# Shared transport for all sessions
sse_transport = SseServerTransport("/messages")


def create_mcp_server(user_id: str, username: str) -> Server:
    """Factory: create an MCP Server instance scoped to a specific user."""
    server = Server(f"iris-hub-{username}")

    @server.list_tools()
    async def handle_list_tools():
        return [
            Tool(
                name="get_recent_items",
                description="Get recent information feed items from the past N hours. Optionally filter by source_type (e.g. 'github_star', 'bilibili').",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "hours_ago": {"type": "integer", "description": "How many hours ago to look back"},
                        "source_type": {"type": "string", "description": "Optional: filter by source type"}
                    },
                    "required": ["hours_ago"]
                }
            ),
            Tool(
                name="add_to_watch_later",
                description="Add an item to the user's Watch Later (starred) list.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string", "description": "The ID of the item to star"}
                    },
                    "required": ["item_id"]
                }
            ),
            Tool(
                name="fetch_item_content",
                description="Fetch the full content or server-cached AI summary for a specific item.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string", "description": "The ID of the item"},
                        "request_server_summary": {"type": "boolean", "description": "If true, return server-cached summary if available"}
                    },
                    "required": ["item_id", "request_server_summary"]
                }
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        if name == "get_recent_items":
            return await _get_recent_items(user_id, arguments)
        elif name == "add_to_watch_later":
            return await _add_to_watch_later(user_id, arguments)
        elif name == "fetch_item_content":
            return await _fetch_item_content(user_id, arguments)
        else:
            return [TextContent(type="text", text=f"Error: Unknown tool '{name}'")]

    return server


async def _get_recent_items(user_id: str, args: dict):
    hours_ago = args.get("hours_ago", 24)
    source_type = args.get("source_type")

    async with AsyncSessionLocal() as session:
        target_time = now_in_app_timezone_naive() - timedelta(hours=hours_ago)
        stmt = (
            select(ItemORM)
            .join(UserItemStateORM, and_(
                UserItemStateORM.item_id == ItemORM.id,
                UserItemStateORM.user_id == user_id
            ))
            .where(ItemORM.created_at >= target_time)
            .order_by(desc(ItemORM.created_at))
        )
        if source_type:
            stmt = stmt.where(ItemORM.source_type == source_type)
        result = await session.execute(stmt)
        items = result.scalars().all()

        arr = [{"id": i.id, "title": i.title, "source": i.source_type, "summary": i.content_text} for i in items]
        return [TextContent(type="text", text=json.dumps(arr, ensure_ascii=False, indent=2))]


async def _add_to_watch_later(user_id: str, args: dict):
    item_id = args.get("item_id", "")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.item_id == item_id,
                    UserItemStateORM.user_id == user_id
                )
            )
            state = result.scalar_one_or_none()
            if not state:
                return [TextContent(type="text", text=f"Error: Cannot access item {item_id}")]
            state.is_starred = True
        return [TextContent(type="text", text=f"Success: Item {item_id} added to Watch Later")]


async def _fetch_item_content(user_id: str, args: dict):
    item_id = args.get("item_id", "")
    request_summary = args.get("request_server_summary", False)

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM).join(UserItemStateORM, and_(
                UserItemStateORM.item_id == ItemORM.id,
                UserItemStateORM.user_id == user_id
            )).where(ItemORM.id == item_id)
        )
        item = result.scalar_one_or_none()
        if not item:
            return [TextContent(type="text", text="Error: Item not found.")]

        if request_summary and item.summary:
            return [TextContent(type="text", text=f"[Server Cached Summary]\n{item.summary}")]

        if item.intent == "article":
            text = item.content_text or "No text available."
        elif item.intent == "video":
            meta = item.metadata_extra or {}
            up_name = meta.get("up_name", "Unknown UP")
            text = (
                f"Title: {item.title}\nAuthor: {up_name}\nDescription: {item.content_text}\n\n"
                "[System Note: Iris Hub direct audio/video transcription (Whisper) is still under development. "
                "Please have the Agent reason and summarize based solely on the video title and description above.]"
            )
        else:
            text = item.content_text or "No text available."

        return [TextContent(type="text", text=text)]


def _extract_user_from_token(token: str) -> dict:
    """Synchronously decode a JWT to extract user info, raise on failure."""
    payload = jose_jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    username = payload.get("sub")
    role = payload.get("role")
    uid = payload.get("uid")
    if not username or not uid:
        raise ValueError("Invalid token")
    return {"id": uid, "username": username, "role": role}


async def handle_sse(request: Request):
    """SSE endpoint with JWT auth — creates a per-user MCP Server."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Missing authorization"}, status_code=401)

    token = auth_header[7:]
    try:
        user_info = _extract_user_from_token(token)
    except Exception:
        return JSONResponse({"detail": "Invalid token"}, status_code=401)

    server = create_mcp_server(user_info["id"], user_info["username"])
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as (read_s, write_s):
        await server.run(read_s, write_s, server.create_initialization_options())
    # SSE lifecycle completed — Starlette will ignore this response since headers already sent
    return Response()


async def handle_messages(request: Request):
    """POST endpoint for MCP messages — forwarded by SseServerTransport."""
    await sse_transport.handle_post_message(
        request.scope, request.receive, request._send
    )
    return Response()


# Build the sub-application
mcp_app = Starlette(
    routes=[
        Route("/sse", endpoint=handle_sse),
        Route("/messages", endpoint=handle_messages, methods=["POST"]),
    ],
)
