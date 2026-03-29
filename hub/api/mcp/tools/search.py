from __future__ import annotations

import json

from mcp.types import TextContent, Tool

from hub.core.search import SearchService

search_service = SearchService()

SEARCH_KNOWLEDGE_BASE_TOOL = Tool(
    name="search_knowledge_base",
    description="Search the user's personal knowledge base using the latest hybrid RRF search pipeline. Returns id, title, source_type, and summary.",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query text"},
            "limit": {"type": "integer", "description": "Maximum number of results to return"},
            "source_type": {"type": "string", "description": "Optional filter by source type"},
        },
        "required": ["query"],
    },
)


async def search_knowledge_base(server, user_id: str, args: dict):
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

    payload = [
        {
            "id": item.id,
            "title": item.title,
            "source_type": item.source_type,
            "summary": item.content_text or item.summary or "",
        }
        for item, _score in results
    ]
    return [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False, indent=2))]
