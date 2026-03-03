import openai
from ..base import BaseLLMProvider

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model

    async def generate_summary(self, text: str) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": f"请简要总结以下内容：\n\n{text[:2000]}"}]
        )
        return response.choices[0].message.content

    async def extract_tags(self, text: str) -> list[str]:
        # 实际逻辑会更复杂点，这里先做演示
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "你是一个标签提取器，仅返回逗号分隔的关键词"},
                      {"role": "user", "content": text[:1000]}]
        )
        tags_raw = response.choices[0].message.content
        return [t.strip() for t in tags_raw.split(",")]