from abc import ABC, abstractmethod
from typing import Any, List

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_summary(self, text: str, length: str = "short", preferred_locale: str | None = None) -> str:
        """生成摘要 (short: 简明摘要，long: 详细报告)"""
        pass

    @abstractmethod
    async def extract_tags(self, text: str, preferred_locale: str | None = None) -> List[str]:
        """提取标签"""
        pass

    @abstractmethod
    async def understand_image(self, image_data_url: str, ocr_text: str = "", preferred_locale: str | None = None) -> dict[str, Any]:
        """理解图片并返回结构化结果"""
        pass
