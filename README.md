## Iris Plugin Development Quickstart

Iris uses a framework-injected plugin system. Plugin authors only need to describe source-specific behavior; common lifecycle controls are injected by the framework.

### Required files

Your plugin package must include:
- `manifest.json`
- `plugin.py` or `__init__.py`

Your entry file must expose a global `plugin` instance.

### Minimal manifest

```json
{
  "id": "my_unique_plugin",
  "name": "My Plugin",
  "description": "Syncs data into Iris",
  "version": "1.0.0",
  "author": "Your Name",
  "permissions": ["network"],
  "framework_defaults": {
    "retention_hours": 24,
    "auto_short_summary": false
  },
  "settings_schema": {
    "api_url": {
      "type": "string",
      "label": "接口地址",
      "default": "https://example.com/api"
    },
    "access_token": {
      "type": "string",
      "label": "访问令牌",
      "secret": true
    }
  }
}
```

### Framework-injected settings

Iris automatically injects these fields into `settings_schema`:
- `auto_short_summary`
- `retention_hours`
- `sync_limit`
- `auto_sync`
- `auto_sync_interval`

Do not define those fields manually in your plugin manifest.

If your plugin needs a different default, use `framework_defaults`:
- GitHub-like long-term content: `{"retention_hours": -1}`
- Short-lived feeds like Bilibili/video dynamics: `{"retention_hours": 24, "auto_short_summary": false}`

### Plugin contract

```python
from shared.plugins.base import BasePlugin, PluginContext


class MyPlugin(BasePlugin):
    async def fetch_data(self, ctx: PluginContext) -> list[dict]:
        return []

    def normalize_item(self, raw_data: dict) -> dict:
        return {
            "id": raw_data["id"],
            "title": raw_data["title"],
            "raw_link": "https://example.com/item",
            "source_type": "my_plugin",
            "intent": "article",
            "content_text": raw_data.get("content", ""),
            "metadata_extra": {},
        }

    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: dict) -> str:
        return raw_data.get("content", "")


plugin = MyPlugin()
```

### Server-Driven UI (Hover Blocks)

Iris supports dynamically rendering rich Hover UIs directly from your plugin without any Vue frontend modifications. 

By providing a JSON array of predefined "Blocks" (`KVBlock`, `ProgressBlock`, `MarkdownBlock`, `QuoteBlock`), the frontend will automatically construct Native elements floating over your item's card.

**Method 1: Pre-computed (Recommended)**
Compute the blocks during the background synchronization phase (for example, inside `extract_text_for_ai`) and save them into the item's metadata so they render instantly with zero network delay.

```python
    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: dict) -> str:
        raw_data.setdefault("metadata_extra", {})["hover_blocks"] = [
            {
                "block_type": "kv",
                "kv_data": {"Stars": 100, "Forks": 20}
            }
        ]
        return raw_data.get("content", "")
```

**Method 2: Real-time API Loading**
For highly dynamic data, you can implement the `get_hover_blocks` signature in your plugin. The Hub will proxy the frontend's hover request to this method if no pre-computed cache exists.

```python
    async def get_hover_blocks(self, item_url: str, user_config: dict) -> list[dict]:
        return [
            {
                "block_type": "markdown",
                "text": "**Real-time** fetched content from specific URL!"
            }
        ]
```

### Runtime architecture

- `worker` executes queued tasks.
- `scheduler` triggers cron-based maintenance and heartbeat jobs.
- `system_heartbeat_task` checks auto-sync plugins every 5 minutes and only dispatches when due.
- `system_ttl_cleanup_task` clears expired data every 5 minutes.
- Embeddings are stored inline in PostgreSQL via `pgvector`, so deleting an `items` row also removes its vector payload.

### Environment

Recommended local `.env` keys:

```env
APP_ENV=dev
APP_TIMEZONE=Asia/Shanghai
LOG_LEVEL=DEBUG
```

- `APP_ENV=dev` enables debug-friendly defaults.
- `APP_ENV=prod` falls back to info-level logs unless `LOG_LEVEL` overrides it.

If `ZoneInfo("Asia/Shanghai")` fails on Windows/uv, install tzdata:

```powershell
uv add tzdata
```
