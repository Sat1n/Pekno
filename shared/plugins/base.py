from abc import ABC, abstractmethod
from typing import List, Dict, Any

class PluginContext:
    """插件运行的安全上下文"""
    def __init__(self, config: dict, http_client, logger, credentials: dict | None = None, env: dict | None = None):
        self.config = config  # 该插件的配置字典 (已从数据库加载，如 sync_limit)
        self.http = http_client  # TODO: 封装的受限 HTTP 客户端
        self.log = logger
        self.credentials = credentials or {}
        self.env = env or {}

class BasePlugin(ABC):
    def __init__(self):
        self._manifest = {} # 留空，等待 Iris 框架注入

    @property
    def manifest(self) -> dict:
        """返回插件的 UI 配置清单 (包含 id, name, settings_schema 等)。

        注意：Iris 会在加载时向 settings_schema 自动注入通用字段：
        - auto_short_summary
        - retention_hours
        - sync_limit
        - auto_sync
        - auto_sync_interval

        插件作者不应手写这些字段；如果想覆盖默认值，请在 manifest 中提供
        framework_defaults，例如 {"retention_hours": 24, "auto_short_summary": false}。
        """
        return self._manifest

    @abstractmethod
    async def fetch_data(self, ctx: PluginContext) -> List[Dict[str, Any]]:
        """使用 ctx.http 抓取原始数据"""
        pass

    @abstractmethod
    def normalize_item(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        数据清洗。必须返回包含以下 key 的字典：
        - id: 唯一标识
        - title: 标题
        - raw_link: 原始链接
        - source_type: 来源类型 (如 'github_star')
        - intent: 内容类型 (如 'article', 'video', 'dynamic')
        - metadata_extra: 插件私有扩展数据 (存入 JSON 字段)
        """
        pass

    @abstractmethod
    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: Dict[str, Any]) -> str:
        """提取并返回用于交给大模型总结的纯文本语料"""
        pass

    @abstractmethod
    async def parse_single_item(self, url: str, ctx: PluginContext | None = None) -> Dict[str, Any]:
        """针对单个 URL 解析并返回符合 Item 规范的字典。"""
        pass

    async def get_hover_blocks(self, item_url: str, user_config: dict) -> list[dict]:
        """
        获取 Server-Driven UI 的 Hover 积木数据。
        默认返回空列表，表示该插件暂不支持 Hover 预览。
        插件可以返回对应 Pydantic Schema (如 KVBlock, QuoteBlock) 序列化后的字典列表。
        """
        return []
