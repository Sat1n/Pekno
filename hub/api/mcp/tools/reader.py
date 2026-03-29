from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from mcp.types import TextContent, Tool
from sqlalchemy import and_, desc, select

from shared.database import AsyncSessionLocal
from shared.models import ItemORM, UserItemStateORM
from shared.time_utils import now_in_app_timezone_naive

READ_ITEM_CONTENT_TOOL = Tool(
    name="read_item_content",
    description="Read full content for a specific item. For articles, returns content_text. For videos, prefers the timestamped Whisper transcript if available, otherwise falls back to summary.",
    inputSchema={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "The ID of the item"},
        },
        "required": ["item_id"],
    },
)

FETCH_ITEM_CONTENT_TOOL = Tool(
    name="fetch_item_content",
    description="Backward-compatible alias of read_item_content.",
    inputSchema={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "The ID of the item"},
            "request_server_summary": {
                "type": "boolean",
                "description": "Legacy flag, ignored when richer content is available",
            },
        },
        "required": ["item_id"],
    },
)

GET_RECENT_ITEMS_TOOL = Tool(
    name="get_recent_items",
    description="Get recent information feed items from the past N hours. Optionally filter by source_type (e.g. 'github_star', 'bilibili').",
    inputSchema={
        "type": "object",
        "properties": {
            "hours_ago": {"type": "integer", "description": "How many hours ago to look back"},
            "source_type": {"type": "string", "description": "Optional filter by source type"},
        },
        "required": ["hours_ago"],
    },
)


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


async def get_recent_items(server, user_id: str, args: dict):
    hours_ago = args.get("hours_ago", 24)
    source_type = args.get("source_type")

    async with AsyncSessionLocal() as session:
        target_time = now_in_app_timezone_naive() - timedelta(hours=hours_ago)
        stmt = (
            select(ItemORM)
            .join(
                UserItemStateORM,
                and_(UserItemStateORM.item_id == ItemORM.id, UserItemStateORM.user_id == user_id),
            )
            .where(ItemORM.created_at >= target_time)
            .order_by(desc(ItemORM.created_at))
        )
        if source_type:
            stmt = stmt.where(ItemORM.source_type == source_type)
        result = await session.execute(stmt)
        items = result.scalars().all()

    payload = [
        {
            "id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "summary": item.content_text or item.summary or "",
        }
        for item in items
    ]
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]


async def read_item_content(server, user_id: str, args: dict):
    item_id = args.get("item_id", "")

    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(ItemORM)
            .join(
                UserItemStateORM,
                and_(UserItemStateORM.item_id == ItemORM.id, UserItemStateORM.user_id == user_id),
            )
            .where(ItemORM.id == item_id)
        )
        item = result.scalar_one_or_none()

    if not item:
        return [TextContent(type="text", text="Error: Item not found.")]

    metadata = item.metadata_extra or {}

    if item.intent == "article":
        text = item.content_text or item.summary or "No text available."
    elif item.intent == "video":
        transcript_text = _format_timestamped_transcript(metadata.get("raw_transcript"))
        text = (
            transcript_text
            or metadata.get("long_summary")
            or item.summary
            or item.content_text
            or "No transcript or summary available."
        )
    else:
        text = item.content_text or "No text available."

    return [TextContent(type="text", text=text)]
