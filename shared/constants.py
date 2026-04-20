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
    "arxiv": {
        "label": "arXiv API Key",
        "config_key": "token",
        "env_var": "PEKNO_ARXIV_API_KEY",
        "legacy_config_key": "token",
    },
    "youtube": {
        "label": "YouTube API Key",
        "config_key": "token",
        "env_var": "PEKNO_YOUTUBE_API_KEY",
        "legacy_config_key": "token",
    },
    "reddit": {
        "label": "Reddit API Token",
        "config_key": "token",
        "env_var": "PEKNO_REDDIT_API_TOKEN",
        "legacy_config_key": "token",
    },
    "twitter": {
        "label": "Twitter API Key",
        "config_key": "token",
        "env_var": "PEKNO_TWITTER_API_KEY",
        "legacy_config_key": "token",
    },
    "mastodon": {
        "label": "Mastodon Access Token",
        "config_key": "token",
        "env_var": "PEKNO_MASTODON_ACCESS_TOKEN",
        "legacy_config_key": "token",
    },
    "bluesky": {
        "label": "Bluesky App Password",
        "config_key": "token",
        "env_var": "PEKNO_BLUESKY_APP_PASSWORD",
        "legacy_config_key": "token",
    },
    "notion": {
        "label": "Notion Integration Token",
        "config_key": "token",
        "env_var": "PEKNO_NOTION_TOKEN",
        "legacy_config_key": "token",
    },
    "readwise": {
        "label": "Readwise Access Token",
        "config_key": "token",
        "env_var": "PEKNO_READWISE_ACCESS_TOKEN",
        "legacy_config_key": "token",
    },
    "pocket": {
        "label": "Pocket Access Token",
        "config_key": "token",
        "env_var": "PEKNO_POCKET_ACCESS_TOKEN",
        "legacy_config_key": "token",
    },
    "instapaper": {
        "label": "Instapaper Access Token",
        "config_key": "token",
        "env_var": "PEKNO_INSTAPAPER_ACCESS_TOKEN",
        "legacy_config_key": "token",
    },
    "zotero": {
        "label": "Zotero API Key",
        "config_key": "token",
        "env_var": "PEKNO_ZOTERO_API_KEY",
        "legacy_config_key": "token",
    },
    "rss": {
        "label": "RSS Feed Credential",
        "config_key": "token",
        "env_var": "PEKNO_RSS_CREDENTIAL",
        "legacy_config_key": "token",
    },
}
