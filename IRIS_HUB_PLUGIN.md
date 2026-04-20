# Iris Hub Plugin Development Guide

This document is the canonical plugin-development reference for CLI agents and coding agents working on Iris Hub plugins.

Iris plugins are Python packages that run inside the worker process. The Hub process exposes plugin management APIs and queues work, but plugin fetching, parsing, OCR/transcription-adjacent enrichment, and ingestion dispatch belong to the worker side.

## Runtime Model

- Plugin code lives under `worker/plugins`.
- Built-in plugins live under `worker/plugins/<name>`.
- Uploaded third-party plugins are installed under `worker/plugins/third_party/<plugin_id>`.
- Plugin metadata is persisted in the `plugins` database table via `PluginRegistryORM`.
- Enabled plugins are imported dynamically by `shared.plugins.manager.PluginManager`.
- Hub and worker both load plugin manifests, but worker executes plugin logic.
- Manual sync calls `run_plugin_pipeline_task(plugin_id, limit, user_id)`.
- Single URL parsing calls `parse_single_plugin_item_task(plugin_id, url, user_id, ...)`.

## Minimal File Layout

For a third-party plugin ZIP:

```text
my_plugin/
  manifest.json
  plugin.py
```

The installer accepts archives where those files are either at the ZIP root or wrapped in one top-level directory.

After installation, Iris stores the plugin at:

```text
worker/plugins/third_party/my_plugin/
```

The registry module path will be:

```text
worker.plugins.third_party.my_plugin.plugin
```

If `plugin.py` is missing, Iris falls back to importing:

```text
worker.plugins.third_party.my_plugin
```

Prefer `plugin.py`.

## Manifest

Each plugin must provide a manifest. You can define it in `manifest.json`, in the plugin class, or both. File-level `manifest.json` is merged into the class manifest and is preferred for package metadata and UI schema.

Example:

```json
{
  "id": "example_bookmarks",
  "name": "Example Bookmarks",
  "source_type": "example_bookmark",
  "description": "Sync bookmarks from Example.",
  "version": "1.0.0",
  "required_credentials": ["github"],
  "auto_sync_supported": true,
  "framework_defaults": {
    "retention_hours": -1,
    "auto_short_summary": true,
    "auto_sync": false,
    "auto_sync_interval": 60,
    "sync_limit": 100
  },
  "settings_schema": {
    "folder": {
      "type": "string",
      "label": "Folder",
      "default": "inbox",
      "scope": "user"
    }
  }
}
```

Required manifest fields:

- `id`: Stable snake_case plugin ID. This becomes the DB key and install directory name.
- `name`: Human-readable name.
- `version`: Plugin version.
- `source_type`: Stable item source type written to `items.source_type`.

Common optional fields:

- `description`: UI description.
- `required_credentials`: List of supported global credential platforms.
- `auto_sync_supported`: Whether the plugin participates in auto-sync UX.
- `framework_defaults`: Overrides framework-injected setting defaults.
- `settings_schema`: Plugin-specific UI settings.

Supported credential platforms currently come from `shared.constants.PLATFORM_WHITELIST`:

- `github`
- `bilibili`
- `arxiv`
- `youtube`
- `reddit`
- `twitter`
- `mastodon`
- `bluesky`
- `notion`
- `readwise`
- `pocket`
- `instapaper`
- `zotero`
- `rss`

Important: `required_credentials` is for credentials, not source types. If a source such as arXiv or RSS can be accessed without authentication, leave `required_credentials` empty and use plugin settings for non-secret options.

## Framework-Injected Settings

Do not manually define these keys in `settings_schema`; the framework injects them:

- `auto_short_summary`
- `retention_hours`
- `sync_limit`
- `auto_sync`
- `auto_sync_interval`

To change defaults, use `framework_defaults`:

```json
{
  "framework_defaults": {
    "retention_hours": 24,
    "auto_short_summary": false,
    "auto_sync": true,
    "auto_sync_interval": 30,
    "sync_limit": 50
  }
}
```

Setting scopes:

- `system`: Saved under the system scope; non-admin users cannot update system-scoped framework settings.
- `user`: Saved per user.

Supported schema types:

- `string`
- `integer`
- `boolean`

Use `"secret": true` only for legacy plugin-specific secrets. New plugins should prefer `required_credentials` and global user credentials.

## Plugin Class

Every plugin must define one concrete subclass of `shared.plugins.base.BasePlugin`.

```python
from typing import Any

from shared.plugins.base import BasePlugin, PluginContext


class ExampleBookmarksPlugin(BasePlugin):
    def __init__(self):
        super().__init__()
        self._manifest = {
            "id": "example_bookmarks",
            "name": "Example Bookmarks",
            "source_type": "example_bookmark",
            "version": "1.0.0",
            "required_credentials": [],
            "settings_schema": {},
        }

    async def fetch_data(self, ctx: PluginContext) -> list[dict[str, Any]]:
        return []

    def normalize_item(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": raw_data["id"],
            "title": raw_data["title"],
            "source_type": "example_bookmark",
            "raw_link": raw_data["url"],
            "content_text": raw_data.get("description", ""),
            "intent": "article",
            "tags": [],
            "metadata_extra": {},
        }

    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: dict[str, Any]) -> str:
        return raw_data.get("description", "")

    async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> dict[str, Any]:
        return {
            "id": f"example_{url}",
            "title": url,
            "source_type": "example_bookmark",
            "raw_link": url,
            "content_text": "",
            "intent": "article",
            "tags": [],
            "metadata_extra": {},
        }
```

## PluginContext

Plugin methods receive `PluginContext`:

```python
ctx.config       # Resolved plugin settings, including framework-injected defaults.
ctx.http         # HTTP client or plugin-specific client.
ctx.log          # Worker logger.
ctx.credentials  # Resolved global credential values by platform.
ctx.env          # Environment-style credential values by env var name.
```

Credential behavior:

- If `required_credentials` is set, users must bind a global credential to the plugin.
- Bound credentials are available in `ctx.credentials`.
- If the platform declares a `config_key`, the credential is also copied into `ctx.config`.
- Example: `github` credentials are available as `ctx.credentials["github"]` and `ctx.config["token"]`.

The GitHub built-in plugin currently receives a specialized `GitHubClient`. Other plugins receive an `httpx.AsyncClient(timeout=15.0)`.

If your plugin receives a generic `httpx.AsyncClient`, close long-lived clients only if you created them yourself. The pipeline closes the context HTTP client after single-item parsing when it exposes `aclose()`.

## Required Methods

### `fetch_data(ctx)`

Fetch raw records for sync.

Rules:

- Respect `ctx.config["sync_limit"]`.
- Return a list of raw dictionaries.
- Do not write to the database.
- Do not enqueue downstream tasks directly.
- Raise exceptions for real failures; the pipeline records sync status and error text.

### `normalize_item(raw_data)`

Convert one raw record into the universal item dictionary.

Required keys:

- `id`: Globally stable item ID.
- `title`: Display title.
- `source_type`: Same stable source type used by the plugin.
- `raw_link`: Canonical URL.
- `intent`: One of the item intent strings, commonly `article`, `video`, `image`, `dynamic`, `code`, or `social_post`.
- `metadata_extra`: Plugin-owned JSON metadata.

Recommended keys:

- `content_text`: Short text or description.
- `tags`: List of strings.
- `cover_url`: Optional display image.
- `retention_hours`: Optional item-level override.
- `auto_short_summary`: Optional item-level override.

### `extract_text_for_ai(ctx, raw_data)`

Return plain text for summarization.

Rules:

- Return an empty string if there is nothing useful to summarize.
- You may enrich `raw_data["metadata_extra"]` here; the pipeline merges it into the final item metadata.
- Keep network calls bounded and logged.

### `parse_single_item(url, ctx=None)`

Parse one user-submitted URL.

Rules:

- Return the same normalized item shape as `normalize_item()`, or return `_pipeline_raw_data` to let the pipeline call `normalize_item()` and `extract_text_for_ai()`.
- Raise `ValueError` for invalid URLs or unsupported formats.
- Use `ctx` when credentials or settings are needed.

Example using `_pipeline_raw_data`:

```python
async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> dict:
    raw = await fetch_remote_object(url, ctx)
    normalized = self.normalize_item(raw)
    normalized["_pipeline_raw_data"] = raw
    return normalized
```

## UniversalItem Mapping

The pipeline converts normalized dicts into `shared.entities.UniversalItem`.

Important fields:

```python
id: str
title: str
source_type: str
raw_link: str
intent: str
cover_url: str | None
retention_hours: int
capabilities: list[str]
content_text: str | None
summary: str | None
tags: list[str]
metadata_extra: dict
auto_short_summary: bool
source_user_id: str | None
```

Pipeline behavior:

- Existing item IDs are skipped during sync.
- For a syncing user, an existing item is linked to that user via `UserItemStateORM`.
- After three consecutive existing items, sync exits early as an incremental circuit breaker.
- Items with text are dispatched to `worker.ingestion.pipeline.process_new_item_task`.
- `metadata_extra["has_long_summary"]` is initialized as `False`.

## Auto-Sync

Auto-sync is controlled by framework settings:

- `auto_sync`
- `auto_sync_interval`

The scheduler/maintenance loop checks enabled plugins and queues `run_plugin_pipeline_task`.

Plugin authors should:

- Set `auto_sync_supported: true` only when repeated background sync is safe.
- Choose conservative defaults in `framework_defaults`.
- Make `fetch_data()` idempotent.
- Use stable item IDs so cache hits work.

## Hover Blocks

Plugins may optionally implement:

```python
async def get_hover_blocks(self, item_url: str, user_config: dict) -> list[dict]:
    return []
```

Return server-driven UI block dictionaries. The GitHub plugin uses:

- `{"block_type": "kv", "kv_data": {...}}`
- `{"block_type": "progress", "items": [{"label": "...", "value": 42.0}]}`

If unsupported, return an empty list.

## Installation and Reload

Admin upload flow:

1. `POST /api/plugins/upload_preview`
2. `POST /api/plugins/confirm_install`

During install:

- ZIP is safely extracted to a temp preview directory.
- `manifest.json` is read without importing plugin code.
- Files are moved into `worker/plugins/third_party/<plugin_id>`.
- Registry row is inserted or updated.
- Hub reloads plugins in-process.
- Worker receives `reload_system_plugins_task`.

Manual development flow for built-in plugins:

1. Add package under `worker/plugins/<plugin_id>`.
2. Add or update a registry row in `plugins` with `module_path`.
3. Restart or trigger plugin reload.

Built-in `github_stars` is auto-registered by `PluginManager.ensure_builtin_plugins()`.

## Security and Safety Rules

- Never execute shell commands from plugin input.
- Never write outside the plugin's own directory or Iris data paths.
- Do not import untrusted code during preview; only install-confirm imports plugin modules.
- Do not store plaintext credentials in plugin metadata or config.
- Use `required_credentials` instead of custom secret settings whenever possible.
- Keep item IDs deterministic and stable.
- Treat `metadata_extra` as user-visible and non-secret.
- Make network requests time-bounded.
- Prefer async APIs.
- Do not block the Hub; heavy work belongs in worker tasks.

## Testing Checklist

Before shipping a plugin:

- `manifest.json` has a stable `id`, `name`, `version`, and `source_type`.
- The plugin defines exactly one concrete `BasePlugin` subclass.
- `fetch_data()` respects `sync_limit`.
- `normalize_item()` returns all required keys.
- `parse_single_item()` works with and without optional credentials as intended.
- Required credentials are declared using supported platform names.
- No secrets are written to `metadata_extra`.
- Manual sync queues and completes.
- Duplicate sync is idempotent and skips existing item IDs.
- Auto-sync defaults are intentional.
- Worker can hot-reload the plugin after install.

## Current Reference Plugin

Use `worker/plugins/github/plugin.py` as the primary reference implementation.

It demonstrates:

- Required global credential binding via `required_credentials`.
- Framework defaults.
- Sync fetching with `fetch_data()`.
- Stable item normalization.
- README extraction in `extract_text_for_ai()`.
- Single URL parsing in `parse_single_item()`.
- Optional hover blocks.
