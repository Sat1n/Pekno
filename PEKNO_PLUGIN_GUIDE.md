# Pekno Plugin Development Guide

This document is the canonical plugin-development reference for CLI agents and coding agents working on Pekno plugins.

Pekno plugins are Python packages that run inside the worker process. The Hub process exposes plugin management APIs and queues work, but plugin fetching, parsing, OCR/transcription-adjacent enrichment, and ingestion dispatch belong to the worker side.

## Runtime Model

- Plugin code lives under `worker/plugins`.
- Built-in plugins live under `worker/plugins/<name>`.
- Uploaded third-party plugins are installed under `worker/plugins/third_party/<plugin_id>`.
- Plugin metadata is persisted in the `plugins` database table via `PluginRegistryORM`.
- Enabled plugins are imported dynamically by `shared.plugins.manager.PluginManager`.
- Hub and worker both load plugin manifests, but worker executes plugin logic.
- Manual sync calls `run_plugin_pipeline_task(plugin_id, limit, user_id, "manual")`.
- Auto-sync calls `run_plugin_pipeline_task(plugin_id, limit, user_id, "auto")`.
- Single URL parsing calls `parse_single_plugin_item_task(plugin_id, url, user_id, ...)`.
- AI ingestion runs through `process_new_item_task`; scheduled incremental batches are fanned out by `trigger_ai_sweep_task`.

## Minimal File Layout

For a third-party plugin ZIP:

```text
my_plugin/
  manifest.json
  plugin.py
```

The installer accepts archives where those files are either at the ZIP root or wrapped in one top-level directory.

After installation, Pekno stores the plugin at:

```text
worker/plugins/third_party/my_plugin/
```

The registry module path will be:

```text
worker.plugins.third_party.my_plugin.plugin
```

If `plugin.py` is missing, Pekno falls back to importing:

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
- `version`: Plugin version (see Versioning below).
- `source_type`: Stable item source type written to `items.source_type`.

### Versioning

Plugins must follow [Semantic Versioning](https://semver.org/) (`MAJOR.MINOR.PATCH`):

- **MAJOR** (`2.0.0`): Breaking changes — removed settings, renamed `source_type`, changed item ID format.
- **MINOR** (`1.1.0`): New features — new settings, new hover blocks, new capabilities.
- **PATCH** (`1.0.1`): Bug fixes — no user-facing behavior changes.

When to bump each segment:

| Change | Bump |
|--------|------|
| Fix a bug in `normalize_item` | PATCH |
| Add `cover_url` to normalized items | PATCH |
| Add a new `settings_schema` field | MINOR |
| Rename a `settings_schema` field | MAJOR |
| Change item ID generation logic | MAJOR |
| Change `source_type` | MAJOR |

The Pekno framework uses version comparison during plugin upgrade:

- Upgrading to a higher version: logged as `⬆️ Upgrading plugin`.
- Reinstalling the same version: logged as `🔄 Reinstalling plugin`.
- Installing a lower version: logged as `⬇️ Downgrading plugin` (warning).
- The framework automatically backs up the previous version (up to 3 versions retained) under `worker/plugins/third_party/.backup/` before overwriting.

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
- `enable_incremental_ai_sync`

To change defaults, use `framework_defaults`:

```json
{
  "framework_defaults": {
    "retention_hours": 24,
    "auto_short_summary": false,
    "auto_sync": true,
    "auto_sync_interval": 30,
    "sync_limit": 50,
    "enable_incremental_ai_sync": false
  }
}
```

Setting scopes:

- `system`: Saved under the system scope; non-admin users cannot update system-scoped framework settings.
- `user`: Saved per user.

`enable_incremental_ai_sync` is system-scoped and defaults to `false`. Plugin authors should not branch on this setting inside plugin code; the Pekno pipeline decides whether to run AI extraction during sync or defer it to the background sweeper.

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

### Sync Modes

Pekno injects `ctx.config["_pekno_sync_mode"]` before calling `fetch_data(ctx)`:

- `latest`: fetch only the newest page or batch. Auto-sync uses this after a plugin already has local history.
- `full`: fetch historical pages until the source is exhausted. Manual sync and initial incremental backfill use this mode.

Plugins should keep one `fetch_data(ctx)` entrypoint and branch inside it:

```python
async def fetch_data(self, ctx: PluginContext) -> list[dict]:
    sync_mode = ctx.config.get("_pekno_sync_mode", "latest")
    if sync_mode == "full":
        return await self._fetch_all_pages(ctx)
    return await self._fetch_latest_page(ctx)
```

Pagination, cursors, offsets, and platform-specific limits belong inside the plugin. If a source cannot support historical sync, fall back to `latest` and log a warning.

## Required Methods

### `fetch_data(ctx)`

Fetch raw records for sync.

Rules:

- Use `ctx.config["_pekno_sync_mode"]` to decide whether to fetch latest data or historical pages.
- Treat `ctx.config["sync_limit"]` as a processing/batch preference, not as an API page-size requirement.
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
- Treat this as the authoritative source-specific extraction hook. Pekno calls it during normal sync, single-item parsing, long summaries, and deferred incremental AI processing.

### `parse_single_item(url, ctx=None)`

Parse one user-submitted URL.

Rules:

- Return the same normalized item shape as `normalize_item()`, or return `_pipeline_raw_data` to let the pipeline call `normalize_item()` and `extract_text_for_ai()`.
- Raise `ValueError` for invalid URLs or unsupported formats.
- Use `ctx` when credentials or settings are needed.
- **Always call the platform API to fetch real content.** Do not return a skeleton item with only URL-derived data. If your plugin has a `_fetch_video_info()`, `_fetch_article()`, or similar helper (used by `get_hover_blocks` or `fetch_data`), reuse it here.
- **Populate `content_text` with meaningful content** (description, summary, article body) — this is what the AI summarizer uses to generate the short summary. An empty `content_text` produces low-quality AI summaries.
- **Include all metadata fields** that `normalize_item` would produce (author, cover_url, published_at, etc.). Single-item parsing should produce items indistinguishable from batch sync items.
- **Wrap API calls in try/except** — if the API call fails, fall back to a minimal item rather than crashing the entire parse task.

Example using `_pipeline_raw_data` with API enrichment:

```python
async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> dict:
    item_id = self._extract_id(url)
    if not item_id:
        raise ValueError("Invalid URL format")

    raw = {"id_hint": item_id, "link": url, "guid": url}

    # Enrich with real platform data if ctx is available
    if ctx:
        try:
            headers = self._headers(ctx)
            async with httpx.AsyncClient(timeout=10.0, headers=headers) as client:
                info = await self._fetch_detail(client, item_id)
            raw["title"] = info.get("title", item_id)
            raw["author"] = info.get("author", "")
            raw["cover_url"] = info.get("cover")
            raw["content_text"] = info.get("description", "")
            raw["published_at"] = info.get("published_at")
        except (httpx.HTTPError, ValueError) as exc:
            ctx.log.warning(f"Failed to fetch detail for {url}: {exc}")
            raw["title"] = item_id
            raw["content_text"] = ""

    normalized = self.normalize_item(raw)
    normalized["_pipeline_raw_data"] = raw
    return normalized
```

**Anti-pattern (do not do this):**

```python
# BAD: Only extracts an ID from the URL, no real content
async def parse_single_item(self, url: str, ctx=None) -> dict:
    vid = self._extract_id(url)
    raw = {"title": vid, "link": url, "content_text": ""}  # ❌ empty content, no real title
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
ai_processing_status: "pending_ai" | "processing" | "completed"
```

Pipeline behavior:

- Existing item IDs are skipped during sync.
- For a syncing user, an existing item is linked to that user via `UserItemStateORM`.
- After three consecutive existing items, sync exits early as an incremental circuit breaker.
- With `enable_incremental_ai_sync=false`, new items call `extract_text_for_ai()` during sync, then dispatch to `worker.ingestion.pipeline.process_new_item_task`.
- With `enable_incremental_ai_sync=true`, sync stores lightweight records as `pending_ai`; the scheduled AI sweeper marks up to 20 records as `processing` and dispatches one `process_new_item_task` per item.
- Successful ingestion writes `ai_processing_status=completed`; failed AI processing returns the item to `pending_ai` for retry.
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

### Plugin Upgrade (Cover Install)

When installing a plugin whose `id` already exists, Pekno performs a cover upgrade:

1. **Version comparison**: The framework reads the existing version from the database and compares it with the new version using semantic versioning.
2. **Automatic backup**: Before overwriting, the old plugin directory is copied to `worker/plugins/third_party/.backup/<plugin_id>_<version>_<timestamp>`. Up to 3 most recent backups are retained per plugin.
3. **Logging**: Upgrade events are logged with version details:
   - `⬆️ Upgrading plugin {id}: {old} → {new}` for version increases.
   - `🔄 Reinstalling plugin {id}` for same-version reinstalls.
   - `⬇️ Downgrading plugin {id}: {old} → {new}` (warning) for version decreases.
4. **File replacement**: Old files are removed, new files are moved into place.
5. **Registry update**: The database record is updated with the new version, name, and module path.
6. **Hot reload**: Hub and Worker reload the updated plugin without restart.

User configuration (settings, credentials) is stored in the `configs` table and is **not affected** by plugin upgrades. Item data in the `items` table is also preserved.

Plugin authors should ensure backward compatibility when upgrading — changing item ID formats or `source_type` values may orphan existing data.

Manual development flow for built-in plugins:

1. Add package under `worker/plugins/<plugin_id>`.
2. Add or update a registry row in `plugins` with `module_path`.
3. Restart or trigger plugin reload.

Built-in `github_star` is auto-registered by `PluginManager.ensure_builtin_plugins()`.

## Security and Safety Rules

- Never execute shell commands from plugin input.
- Never write outside the plugin's own directory or Pekno data paths.
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
