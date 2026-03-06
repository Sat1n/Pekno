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

    async def generate_summary(self, text: str, length: str = "short") -> str:
        if length == "short":
            prompt = f"请提取这段内容的最核心信息，生成一段30-50字的极简摘要。必须直接输出摘要结果，不要输出任何如'好的'、'这段内容'之类的解释词汇：\n{text[:2000]}"
        else:
            prompt = (
                f"你是一个开源项目分析专家。请根据这段 README 内容详细总结项目的:\n"
                f"1. 核心功能与亮点\n2. 技术架构栈\n3. 简易部署与使用方式\n\n"
                f"字数不限，要求排版精美的 Markdown 格式，层级清晰，重点突出：\n{text[:8000]}"
            )
            
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    async def extract_tags(self, text: str) -> list[str]:
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": f"提取3个关键词，逗号隔开：\n{text[:500]}"}]
        )
        return [t.strip() for t in response.choices[0].message.content.split(",")]