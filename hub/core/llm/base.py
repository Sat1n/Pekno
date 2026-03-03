from abc import ABC, abstractmethod
from typing import List, Optional

class BaseLLMProvider(ABC):
    @abstractmethod
    async def generate_summary(self, text: str) -> str:
        """生成摘要"""
        pass

    @abstractmethod
    async def extract_tags(self, text: str) -> List[str]:
        """提取标签"""
        pass