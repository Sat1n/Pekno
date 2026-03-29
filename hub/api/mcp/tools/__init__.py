from __future__ import annotations

from hub.api.mcp.tools.action import ADD_TO_WATCH_LATER_TOOL, MARK_AS_STARRED_TOOL, mark_as_starred
from hub.api.mcp.tools.admin import UPDATE_PLUGIN_CONFIG_TOOL, update_plugin_config
from hub.api.mcp.tools.reader import (
    FETCH_ITEM_CONTENT_TOOL,
    GET_RECENT_ITEMS_TOOL,
    READ_ITEM_CONTENT_TOOL,
    get_recent_items,
    read_item_content,
)
from hub.api.mcp.tools.search import SEARCH_KNOWLEDGE_BASE_TOOL, search_knowledge_base

TOOL_DEFINITIONS = [
    SEARCH_KNOWLEDGE_BASE_TOOL,
    READ_ITEM_CONTENT_TOOL,
    GET_RECENT_ITEMS_TOOL,
    MARK_AS_STARRED_TOOL,
    ADD_TO_WATCH_LATER_TOOL,
    FETCH_ITEM_CONTENT_TOOL,
    UPDATE_PLUGIN_CONFIG_TOOL,
]

TOOL_HANDLERS = {
    "search_knowledge_base": search_knowledge_base,
    "read_item_content": read_item_content,
    "fetch_item_content": read_item_content,
    "get_recent_items": get_recent_items,
    "mark_as_starred": mark_as_starred,
    "add_to_watch_later": mark_as_starred,
    "update_plugin_config": update_plugin_config,
}
