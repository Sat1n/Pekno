import openai
from ..base import BaseLLMProvider
import re
import json

from hub.core.billing import (
    check_api_limit_or_raise,
    estimate_tokens,
    read_response_usage,
    record_api_usage,
)


def _parse_tag_list(raw_text: str) -> list[str]:
    parts = re.split(r"[,，\n]+", raw_text or "")
    cleaned: list[str] = []
    for part in parts:
        tag = part.strip().strip("#")
        if not tag or tag in cleaned:
            continue
        cleaned.append(tag)
    return cleaned[:8]

class OllamaProvider(BaseLLMProvider):
    def __init__(self, host: str, model: str):
        # Ollama 默认 OpenAI 兼容地址通常是 http://localhost:11434/v1
        self.client = openai.AsyncOpenAI(
            api_key="ollama", # Ollama 不需要真正的 Key
            base_url=f"{host}/v1"
        )
        self.model_name = model

    async def generate_summary(self, text: str, length: str = "short") -> str:
        await check_api_limit_or_raise()
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
        content = response.choices[0].message.content or ""
        usage = read_response_usage(response)
        if usage:
            await record_api_usage(self.model_name, *usage, force_zero_cost=True)
        else:
            await record_api_usage(
                self.model_name,
                prompt_tokens=estimate_tokens(prompt),
                completion_tokens=estimate_tokens(content),
                force_zero_cost=True,
            )
        return content

    async def extract_tags(self, text: str) -> list[str]:
        await check_api_limit_or_raise()
        prompt = f"提取3个关键词，逗号隔开：\n{text[:500]}"
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[{"role": "user", "content": prompt}]
        )
        content = response.choices[0].message.content or ""
        usage = read_response_usage(response)
        if usage:
            await record_api_usage(self.model_name, *usage, force_zero_cost=True)
        else:
            await record_api_usage(
                self.model_name,
                prompt_tokens=estimate_tokens(prompt),
                completion_tokens=estimate_tokens(content),
                force_zero_cost=True,
            )
        return _parse_tag_list(content)

    async def understand_image(self, image_data_url: str, ocr_text: str = "") -> dict:
        await check_api_limit_or_raise()
        prompt = (
            "你是一个图片理解助手。请分析图片，并只返回 JSON 对象。"
            'JSON schema: {"short_caption": string, "detailed_summary_markdown": string, "tags": string[], '
            '"ocr_text": string, "objects": string[], "scene": string}. '
            "不要输出额外说明。"
        )
        if ocr_text.strip():
            prompt += f"\n\n已通过本地 OCR 识别到部分文字，可作为辅助参考：\n{ocr_text[:4000]}"
        response = await self.client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": image_data_url}},
                    ],
                }
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"
        usage = read_response_usage(response)
        if usage:
            await record_api_usage(self.model_name, *usage, force_zero_cost=True)
        else:
            await record_api_usage(
                self.model_name,
                prompt_tokens=estimate_tokens(prompt),
                completion_tokens=estimate_tokens(raw),
                force_zero_cost=True,
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}
