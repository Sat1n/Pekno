import re

from shared.config import ConfigKeys, ConfigManager
from shared.constants import PLATFORM_WHITELIST
from shared.credentials import get_user_credential, validate_required_credentials
from shared.database import AsyncSessionLocal
from shared.plugins.base import PluginContext
from shared.plugins.manager import plugin_manager
from shared.logger import worker_log


class MissingPluginCredentialError(RuntimeError):
    pass


async def build_plugin_context_for_user(plugin_id: str, plugin, user_id: str | None):
    config_dict = {}
    for key, schema in plugin.manifest.get("settings_schema", {}).items():
        val = await ConfigManager.get_config(plugin_id, key, user_id=user_id)
        if val is not None:
            config_dict[key] = int(val) if schema.get("type") == "integer" else (val == "true" if schema.get("type") == "boolean" else val)
        else:
            config_dict[key] = schema.get("default")

    runtime_credentials = {}
    runtime_env = {}
    required_credentials = validate_required_credentials(plugin.manifest.get("required_credentials"))
    for platform in required_credentials:
        binding_enabled = await ConfigManager.get_config(
            plugin_id,
            ConfigKeys.credential_binding(platform),
            user_id=user_id,
        )
        credential = None
        if binding_enabled == "true" and user_id:
            credential = await get_user_credential(user_id, platform)
            if credential is None:
                raise MissingPluginCredentialError(
                    f"[{plugin_id}] Missing required global credential for platform '{platform}'"
                )

        if credential is None:
            legacy_key = PLATFORM_WHITELIST[platform].get("legacy_config_key")
            if legacy_key:
                legacy_value = await ConfigManager.get_config(plugin_id, legacy_key, user_id=user_id)
                if legacy_value:
                    runtime_credentials[platform] = legacy_value
                    config_key = PLATFORM_WHITELIST[platform].get("config_key")
                    if config_key and not config_dict.get(config_key):
                        config_dict[config_key] = legacy_value
                    continue

        if credential is not None:
            runtime_credentials[platform] = credential.token_value
            config_key = PLATFORM_WHITELIST[platform].get("config_key")
            env_var = PLATFORM_WHITELIST[platform].get("env_var")
            if config_key and not config_dict.get(config_key):
                config_dict[config_key] = credential.token_value
            if env_var:
                runtime_env[env_var] = credential.token_value

    import httpx
    http_client = None
    if plugin_id == "github_star":
        from worker.plugins.github.client import GitHubClient
        token = config_dict.get("token")
        if not token:
            raise ValueError(f"[{plugin_id}] Token is not configured and link parsing cannot continue")
        http_client = GitHubClient(token)
    else:
        http_client = httpx.AsyncClient(timeout=15.0)

    return PluginContext(
        config=config_dict,
        http_client=http_client,
        logger=worker_log,
        credentials=runtime_credentials,
        env=runtime_env,
    )



def resolve_sync_fetch_mode(
    *,
    incremental_ai_sync: bool,
    sync_mode: str,
    has_existing_items: bool,
) -> tuple[str, bool]:
    should_backfill = incremental_ai_sync and (sync_mode == "manual" or not has_existing_items)
    return ("full" if should_backfill else "latest", should_backfill)


def build_item_raw_data(item) -> dict:
    metadata = dict(item.metadata_extra or {})
    raw_data = {
        "id": item.id,
        "title": item.title,
        "name": item.title,
        "raw_link": item.raw_link,
        "url": item.raw_link,
        "source_type": item.source_type,
        "intent": item.intent,
        "description": item.content_text or item.summary or "",
        "content_text": item.content_text or "",
        "summary": item.summary or "",
        "metadata_extra": metadata,
    }

    repo_match = re.search(r"github\.com/([^/]+)/([^/]+)", item.raw_link or "")
    if repo_match:
        raw_data["owner"] = {"login": repo_match.group(1)}
        raw_data["name"] = repo_match.group(2)

    return raw_data


def fallback_text_for_summary(item) -> str:
    return "\n\n".join(
        part for part in [
            f"标题：{item.title}" if item.title else "",
            f"简介：{item.content_text or item.summary}" if (item.content_text or item.summary) else "",
        ]
        if part
    ).strip()


async def close_plugin_context(ctx) -> None:
    close_method = getattr(ctx.http, "aclose", None)
    if close_method:
        await close_method()
