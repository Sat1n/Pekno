from __future__ import annotations

from mcp.types import TextContent, Tool
from sqlalchemy import select

from hub.api.mcp.context import get_scopes
from shared.database import AsyncSessionLocal
from shared.models import UserItemStateORM

MARK_AS_STARRED_TOOL = Tool(
    name="mark_as_starred",
    description="Mark an item as watch later. Requires the write:star scope.",
    inputSchema={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "The ID of the item to star"},
        },
        "required": ["item_id"],
    },
)

ADD_TO_WATCH_LATER_TOOL = Tool(
    name="add_to_watch_later",
    description="Backward-compatible alias of mark_as_starred. Requires the write:star scope.",
    inputSchema={
        "type": "object",
        "properties": {
            "item_id": {"type": "string", "description": "The ID of the item to star"},
        },
        "required": ["item_id"],
    },
)


async def mark_as_starred(server, user_id: str, args: dict):
    scopes = get_scopes(server)
    if "write:star" not in scopes:
        return [
            TextContent(
                type="text",
                text="Permission Denied: 您的 Token 缺少 write:star 权限，无法执行收藏操作。",
            )
        ]

    item_id = args.get("item_id", "")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(UserItemStateORM).where(
                    UserItemStateORM.item_id == item_id,
                    UserItemStateORM.user_id == user_id,
                )
            )
            state = result.scalar_one_or_none()
            if not state:
                return [TextContent(type="text", text=f"Error: Cannot access item {item_id}")]
            state.is_watch_later = True

    return [TextContent(type="text", text=f"Success: Item {item_id} added to Watch Later")]
