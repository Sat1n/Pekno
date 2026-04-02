import openai
from ..base import BaseLLMProvider
import re
import json


def _parse_tag_list(raw_text: str) -> list[str]:
    parts = re.split(r"[,，\n]+", raw_text or "")
    cleaned: list[str] = []
    for part in parts:
        tag = part.strip().strip("#")
        if not tag or tag in cleaned:
            continue
        cleaned.append(tag)
    return cleaned[:8]

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, base_url: str, model: str):
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
        self.model = model
        self.model_name = model

    async def generate_summary(self, text: str, length: str = "short") -> str:
        if length == "short":
            prompt = f"请提取这段内容的最核心信息，生成一段30-50字的极简摘要。必须直接输出摘要结果，不要输出任何额外解释：\n{text[:2000]}"
        else:
            prompt = (
                f"你是一个信息分析助手。请根据以下内容输出结构化、重点清晰的 Markdown 总结，"
                f"涵盖核心结论、重要细节与可执行信息：\n{text[:8000]}"
            )
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.choices[0].message.content

    async def extract_tags(self, text: str) -> list[str]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": "你是一个标签提取器，仅返回逗号分隔的关键词"},
                      {"role": "user", "content": text[:1000]}]
        )
        tags_raw = response.choices[0].message.content
        return _parse_tag_list(tags_raw)

    async def understand_image(self, image_data_url: str) -> dict:
        prompt = (
            "你是一个图片理解助手。请仔细分析图片，并只返回 JSON 对象，不要输出 Markdown 或解释。"
            'JSON schema: {"short_caption": string, "detailed_summary_markdown": string, "tags": string[], '
            '"ocr_text": string, "objects": string[], "scene": string}. '
            "要求：short_caption 为 20-60 字简洁描述；detailed_summary_markdown 为面向知识库的 Markdown 总结；"
            "如果图片里有文字，尽量提取到 ocr_text；如果没有就返回空字符串。"
        )
        response = await self.client.chat.completions.create(
            model=self.model,
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
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}
