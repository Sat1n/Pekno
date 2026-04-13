from __future__ import annotations

from typing import Final


PLATFORM_WHITELIST: Final[dict[str, dict[str, str]]] = {
    "github": {
        "label": "GitHub Token",
        "config_key": "token",
        "env_var": "PEKNO_GITHUB_TOKEN",
        "legacy_config_key": "token",
    },
    "bilibili": {
        "label": "Bilibili SESSDATA",
        "config_key": "cookie",
        "env_var": "PEKNO_BILIBILI_SESSDATA",
        "legacy_config_key": "cookie",
    },
    "twitter": {
        "label": "Twitter API Key",
        "config_key": "token",
        "env_var": "PEKNO_TWITTER_API_KEY",
        "legacy_config_key": "token",
    },
}

