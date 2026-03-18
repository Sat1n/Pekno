from abc import ABC, abstractmethod
from typing import List, Dict, Any

class PluginContext:
    """插件运行的安全上下文"""
    def __init__(self, config: dict, http_client, logger):
        self.config = config  # 该插件的配置字典 (已从数据库加载，如 sync_limit)
        self.http = http_client  # TODO: 封装的受限 HTTP 客户端
        self.log = logger

class BasePlugin(ABC):
    def __init__(self):
        self._manifest = {} # 留空，等待 Iris 框架注入

    @property
    def manifest(self) -> dict:
        """返回插件的 UI 配置清单 (包含 id, name, settings_schema 等)"""
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
        - metadata_extra: 插件私有扩展数据 (存入 JSON 字段)
        """
        pass

    @abstractmethod
    async def extract_text_for_ai(self, ctx: PluginContext, raw_data: Dict[str, Any]) -> str:
        """提取并返回用于交给大模型总结的纯文本语料"""
        pass
