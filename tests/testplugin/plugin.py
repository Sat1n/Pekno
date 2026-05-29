import uuid
import json
from typing import Any

from shared.plugins.base import BasePlugin, PluginContext


class UITesterPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        # We rely on the manifest.json we created, so we don't need to define it here if the framework reads it.
        # But to be safe and fully self-contained as a backup, we can define a minimal manifest.
        self._manifest = {
            "id": "ui_components_tester",
            "name": "UI Components Tester",
            "source_type": "ui_tester",
            "version": "1.0.0",
            "required_credentials": [],
        }

    async def fetch_data(self, ctx: PluginContext) -> list[dict[str, Any]]:
        # Fetch configurations selected by the user in the UI
        config = ctx.config
        
        # We generate a few fake items that reflect the configuration
        return [
            {
                "id": f"fake_item_{uuid.uuid4().hex[:8]}",
                "title": "UI Components Config Reflection",
                "url": "https://example.com/ui-tester/reflection",
                "description": f"This item reflects the settings: {json.dumps(config, ensure_ascii=False)}",
                "config_snapshot": config,
            },
            {
                "id": f"fake_item_{uuid.uuid4().hex[:8]}",
                "title": "Another Fake Data Item",
                "url": "https://example.com/ui-tester/data",
                "description": "Just some more fake data to test the sync pipeline.",
                "config_snapshot": config,
            }
        ]

    def normalize_item(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": raw_data["id"],
            "title": raw_data["title"],
            "source_type": "ui_tester",
            "raw_link": raw_data["url"],
            "content_text": raw_data.get("description", ""),
            "intent": "article",
            "tags": ["test", "ui", "mock"],
            "metadata_extra": {"config_snapshot": raw_data.get("config_snapshot")},
        }

    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: dict[str, Any]) -> str:
        return raw_data.get("description", "")

    async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> dict[str, Any]:
        raw = {
            "id": f"single_parse_{uuid.uuid4().hex[:8]}",
            "title": f"Parsed: {url}",
            "url": url,
            "description": "This is a single parsed item.",
            "config_snapshot": ctx.config if ctx else {},
        }
        normalized = self.normalize_item(raw)
        normalized["_pipeline_raw_data"] = raw
        return normalized
