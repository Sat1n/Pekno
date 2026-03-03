import openai
from ..base import BaseLLMProvider

class OllamaProvider(BaseLLMProvider):
    def __init__(self, host: str, model: str):
        # Ollama 默认 OpenAI 兼容地址通常是 http://localhost:11434/v1
        self.client = openai.AsyncOpenAI(
            api_key="ollama", # Ollama 不需要真正的 Key
            base_url=f"{host}/v1"
        )
        self.model_name = model

    async def generate_summary(self, text: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": f"请简要总结内容：\n{text[:2000]}"}]
        )
        return response.choices[0].message.content

    async def extract_tags(self, text: str) -> list[str]:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": f"提取3个关键词，逗号隔开：\n{text[:500]}"}]
        )
        return [t.strip() for t in response.choices[0].message.content.split(",")]