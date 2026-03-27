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
from typing import Any

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
from hub.core.search import SearchService
from shared.time_utils import now_in_app_timezone_naive
from sqlalchemy import select, and_, desc

from jose import jwt as jose_jwt

logger = logging.getLogger("iris-mcp")
search_service = SearchService()

# Shared transport for all sessions
sse_transport = SseServerTransport("/messages")


def create_mcp_server(user_id: str, username: str) -> Server:
    """Factory: create an MCP Server instance scoped to a specific user."""
    server = Server(f"iris-hub-{username}")

    @server.list_tools()
    async def handle_list_tools():
        return [
            Tool(
                name="search_knowledge_base",
                description="Search the user's personal knowledge base using the latest hybrid RRF search pipeline. Returns id, title, source_type, and summary.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query text"},
                        "limit": {"type": "integer", "description": "Maximum number of results to return"},
                        "source_type": {"type": "string", "description": "Optional: filter by source type"}
                    },
                    "required": ["query"]
                }
            ),
            Tool(
                name="read_item_content",
                description="Read full content for a specific item. For articles, returns content_text. For videos, prefers the timestamped Whisper transcript if available, otherwise falls back to summary.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string", "description": "The ID of the item"}
                    },
                    "required": ["item_id"]
                }
            ),
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
                description="Backward-compatible alias of read_item_content.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "item_id": {"type": "string", "description": "The ID of the item"},
                        "request_server_summary": {"type": "boolean", "description": "Legacy flag, ignored when richer content is available"}
                    },
                    "required": ["item_id"]
                }
            ),
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: dict):
        if name == "search_knowledge_base":
            return await _search_knowledge_base(user_id, arguments)
        elif name == "read_item_content":
            return await _read_item_content(user_id, arguments)
        elif name == "get_recent_items":
            return await _get_recent_items(user_id, arguments)
        elif name == "add_to_watch_later":
            return await _add_to_watch_later(user_id, arguments)
        elif name == "fetch_item_content":
            return await _read_item_content(user_id, arguments)
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

        arr = [{"id": i.id, "title": i.title, "source_type": i.source_type, "summary": i.content_text or i.summary} for i in items]
        return [TextContent(type="text", text=json.dumps(arr, ensure_ascii=False, indent=2))]


async def _search_knowledge_base(user_id: str, args: dict):
    query = str(args.get("query", "")).strip()
    limit = int(args.get("limit", 8) or 8)
    source_type = args.get("source_type")

    if not query:
        return [TextContent(type="text", text="Error: query is required.")]

    results = await search_service.hybrid_search(
        query_text=query,
        user_id=user_id,
        limit=max(1, min(limit, 20)),
        source_type=source_type,
    )

    payload = []
    for item, _score in results:
        payload.append(
            {
                "id": item.id,
                "title": item.title,
                "source_type": item.source_type,
                "summary": item.content_text or item.summary or "",
            }
        )

    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


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


def _format_timestamped_transcript(raw_transcript: Any) -> str | None:
    if not raw_transcript:
        return None

    try:
        segments = json.loads(raw_transcript) if isinstance(raw_transcript, str) else raw_transcript
    except Exception:
        return None

    if not isinstance(segments, list):
        return None

    lines: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        start = float(segment.get("start", 0) or 0)
        total_seconds = max(0, int(start))
        minutes, seconds = divmod(total_seconds, 60)
        hours, minutes = divmod(minutes, 60)
        timestamp = f"{hours:02d}:{minutes:02d}:{seconds:02d}" if hours > 0 else f"{minutes:02d}:{seconds:02d}"
        lines.append(f"[{timestamp}] {text}")

    return "\n".join(lines).strip() or None


async def _read_item_content(user_id: str, args: dict):
    item_id = args.get("item_id", "")

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

        metadata = item.metadata_extra or {}

        if item.intent == "article":
            text = item.content_text or item.summary or "No text available."
        elif item.intent == "video":
            transcript_text = _format_timestamped_transcript(metadata.get("raw_transcript"))
            if transcript_text:
                text = transcript_text
            else:
                text = (
                    metadata.get("long_summary")
                    or item.summary
                    or item.content_text
                    or "No transcript or summary available."
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
