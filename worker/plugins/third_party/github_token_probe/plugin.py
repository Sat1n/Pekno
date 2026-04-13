from __future__ import annotations

from typing import Any

from shared.plugins.base import BasePlugin, PluginContext


class GitHubTokenProbePlugin(BasePlugin):
    """
    Minimal diagnostic plugin for validating shared GitHub credential reuse.

    It does not fetch or ingest any real content. The only purpose is to prove
    that runtime credential injection works across different plugins for the
    same user-scoped GitHub token.
    """

    def __init__(self) -> None:
        super().__init__()
        self._manifest = {
            "id": "github_token_probe",
            "name": "GitHub Token Probe",
            "source_type": "github_token_probe",
            "description": "A minimal diagnostic plugin used to verify shared GitHub credential injection.",
            "version": "1.0.0",
            "required_credentials": ["github"],
            "auto_sync_supported": False,
            "framework_defaults": {
                "retention_hours": -1,
                "auto_short_summary": False,
            },
            "settings_schema": {},
        }

    async def fetch_data(self, ctx: PluginContext) -> list[dict[str, Any]]:
        token = ctx.credentials.get("github") or ctx.config.get("token") or ctx.env.get("PEKNO_GITHUB_TOKEN")
        if not token:
            ctx.log.warning("[github_token_probe] No GitHub credential was injected into the runtime context.")
            return []

        masked = f"{token[:4]}***{token[-3:]}" if len(token) > 8 else "*" * len(token)
        ctx.log.info("[github_token_probe] Shared GitHub credential detected successfully: %s", masked)
        return []

    def normalize_item(self, raw_data: dict[str, Any]) -> dict[str, Any]:
        return raw_data

    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: dict[str, Any]) -> str:
        return ""

    async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> dict[str, Any]:
        token = None
        if ctx is not None:
            token = ctx.credentials.get("github") or ctx.config.get("token") or ctx.env.get("PEKNO_GITHUB_TOKEN")
        masked = f"{token[:4]}***{token[-3:]}" if token and len(token) > 8 else ("*" * len(token) if token else None)
        return {
            "id": "github-token-probe-single",
            "title": "GitHub Token Probe",
            "source_type": "github_token_probe",
            "raw_link": url,
            "content_text": "Credential probe only.",
            "intent": "article",
            "metadata_extra": {
                "probe_result": "credential_detected" if token else "credential_missing",
                "masked_token": masked,
            },
        }
