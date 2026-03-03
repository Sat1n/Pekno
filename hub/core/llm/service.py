from .providers.openai_adapter import OpenAIProvider
from .providers.ollama_adapter import OllamaProvider
from langchain_ollama import OllamaEmbeddings
import os
import asyncio
from typing import List

class LLMService:
    def __init__(self):
        # 模拟从用户配置读取，现在先写死为 Ollama 方便你测试
        self.config = {
            "type": "ollama",
            "host": "http://127.0.0.1:11434",
            "model": "qwen3:8b" # 或者是你本地 pull 的模型名，如 qwen2.5
        }
        self.provider = self._get_provider()

    def _get_provider(self):
        if self.config["type"] == "ollama":
            return OllamaProvider(self.config["host"], self.config["model"])
        elif self.config["type"] == "openai":
            return OpenAIProvider(...)
        raise ValueError("Unknown provider")

    @property
    def current_model(self) -> str:
        return self.provider.model_name

class EmbeddingService:
    def __init__(self):
        # 同样支持从配置读取，这里先写死 Ollama
        self.model_name = "nomic-embed-text-v2-moe" # 或者你 local pull 的模型
        self.client = OllamaEmbeddings(
            model=self.model_name,
            base_url="http://127.0.0.1:11434"
        )

    async def get_vector(self, text: str) -> List[float]:
        """将文本转为 1536 维(或对应维度)的向量"""
        # 注意：LangChain 的 embed_query 是同步阻塞的，在异步环境下建议跑在线程池
        return await asyncio.to_thread(self.client.embed_query, text)

class LLMManager:
    def __init__(self):
        # 这里的配置以后从用户的 DB 设置里读
        self.llm = LLMService()
        self.embed = EmbeddingService()
    
    @property
    def model_name(self):
        return self.llm.current_model

    @property
    def embed_model_name(self):
        return self.embed.model_name