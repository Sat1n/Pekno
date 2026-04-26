from __future__ import annotations

from typing import Final, Any


PLATFORM_WHITELIST: Final[dict[str, dict[str, Any]]] = {
    "github": {
        "label": "GitHub Token",
        "config_key": "token",
        "env_var": "PEKNO_GITHUB_TOKEN",
        "legacy_config_key": "token",
    },
    "bilibili": {
        "label": "Bilibili Cookie",
        "config_key": "cookie",
        "credential_kind": "cookie_file",
        "env_var": "PEKNO_BILIBILI_COOKIE_FILE",
        "legacy_config_key": "cookie",
        "cookie_dir": "bilibili",
        "required_cookie_keys": [
            "SESSDATA",
            "buvid3",
            "bili_jct",
            "DedeUserID",
        ],
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
