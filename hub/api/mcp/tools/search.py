from __future__ import annotations

import json
from datetime import datetime

from mcp.types import TextContent, Tool

from hub.core.search import SearchService

search_service = SearchService()

SEARCH_KNOWLEDGE_BASE_TOOL = Tool(
    name="search_knowledge_base",
    description="Search the user's personal knowledge base using the latest hybrid RRF search pipeline. Returns id, title, source_type, and summary. Supports filtering by author, intent, vault_category_id, is_read, and date range.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query text"},
            "limit": {"type": "integer", "description": "Maximum number of results to return"},
            "source_type": {"type": "string", "description": "Optional filter by source type"},
            "author": {"type": "string", "description": "Optional filter by author name (partial match)"},
            "intent": {"type": "string", "description": "Optional filter by content intent (video/article/image/code/social_post/dynamic)"},
            "vault_category_id": {"type": "string", "description": "Optional filter by vault category ID"},
            "is_read": {"type": "boolean", "description": "Optional filter by read status"},
            "date_from": {"type": "string", "description": "Optional start date filter (ISO format)"},
            "date_to": {"type": "string", "description": "Optional end date filter (ISO format)"},
        },
        "required": ["query"],
    },
)


async def search_knowledge_base(server, user_id: str, args: dict):
    query = str(args.get("query", "")).strip()
    limit = int(args.get("limit", 8) or 8)
    source_type = args.get("source_type")
    author = args.get("author")
    intent = args.get("intent")
    vault_category_id = args.get("vault_category_id")
    is_read = args.get("is_read")
    date_from = args.get("date_from")
    date_to = args.get("date_to")

    if not query:
        return [TextContent(type="text", text="Error: query is required.")]

    # 解析时间参数
    parsed_date_from = None
    parsed_date_to = None
    if date_from:
        try:
            parsed_date_from = datetime.fromisoformat(date_from.replace('Z', '+00:00'))
        except ValueError:
            pass
    if date_to:
        try:
            parsed_date_to = datetime.fromisoformat(date_to.replace('Z', '+00:00'))
        except ValueError:
            pass

    results = await search_service.hybrid_search(
        query_text=query,
        user_id=user_id,
        limit=max(1, min(limit, 20)),
        source_type=source_type,
        author=author,
        intent=intent,
        vault_category_id=vault_category_id,
        is_read=is_read,
        date_from=parsed_date_from,
        date_to=parsed_date_to,
    )

    payload = [
        {
            "id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "author": item.author or "",
            "intent": item.intent,
            "summary": item.content_text or item.summary or "",
        }
        for item, _score in results
    ]
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]
