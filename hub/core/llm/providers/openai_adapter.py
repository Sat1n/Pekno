from .openai_client import create_openai_client
from ..base import BaseLLMProvider
import re
import json
from shared.locale import build_output_language_instruction
from hub.core.llm.summary_call import request_summary

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

class OpenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str | None, base_url: str, model: str, enable_thinking: bool | None = None):
        self.client = create_openai_client(api_key, base_url)
        self.model = model
        self.model_name = model
        self.completion_options = (
            {"extra_body": {"chat_template_kwargs": {"enable_thinking": enable_thinking}}}
            if enable_thinking is not None else {}
        )

    async def generate_summary(self, text: str, length: str = "short", preferred_locale: str | None = None) -> str:
        await check_api_limit_or_raise()
        language_instruction = build_output_language_instruction(preferred_locale)
        if length == "short":
            prompt = (
                "请提取这段内容的最核心信息，生成一段30-50字的极简摘要。"
                "必须直接输出摘要结果，不要输出任何额外解释。\n"
                f"{language_instruction}\n{text[:2000]}"
            )
        else:
            prompt = (
                f"你是一个信息分析助手。请根据以下内容输出结构化、重点清晰的 Markdown 总结，"
                f"涵盖核心结论、重要细节与可执行信息。\n"
                f"{language_instruction}\n{text[:8000]}"
            )
        async def record_summary_usage(response, content):
            usage = read_response_usage(response)
            if usage:
                await record_api_usage(self.model, *usage)
            else:
                await record_api_usage(
                    self.model,
                    prompt_tokens=estimate_tokens(prompt),
                    completion_tokens=estimate_tokens(content),
                )

        response, content = await request_summary(
            lambda: self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                **self.completion_options,
            ),
            model=self.model,
            purpose="short_summary" if length == "short" else "long_summary",
            record_usage=record_summary_usage,
        )
        return content

    async def extract_tags(self, text: str, preferred_locale: str | None = None) -> list[str]:
        await check_api_limit_or_raise()
        prompt_text = text[:1000]
        system_prompt = (
            "你是一个标签提取器，仅返回逗号分隔的关键词。"
            f" {build_output_language_instruction(preferred_locale, style='tags')}"
        )
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": prompt_text}],
            **self.completion_options,
        )
        tags_raw = response.choices[0].message.content or ""
        usage = read_response_usage(response)
        if usage:
            await record_api_usage(self.model, *usage)
        else:
            await record_api_usage(
                self.model,
                prompt_tokens=estimate_tokens(prompt_text) + estimate_tokens(system_prompt),
                completion_tokens=estimate_tokens(tags_raw),
            )
        return _parse_tag_list(tags_raw)

    async def understand_image(self, image_data_url: str, ocr_text: str = "", preferred_locale: str | None = None) -> dict:
        await check_api_limit_or_raise()
        prompt = (
            "你是一个图片理解助手。请仔细分析图片，并只返回 JSON 对象，不要输出 Markdown 或解释。"
            'JSON schema: {"short_caption": string, "detailed_summary_markdown": string, "tags": string[], '
            '"ocr_text": string, "objects": string[], "scene": string}. '
            "要求：short_caption 为 20-60 字简洁描述；detailed_summary_markdown 为面向知识库的 Markdown 总结；"
            "如果图片里有文字，尽量提取到 ocr_text；如果没有就返回空字符串。 "
            f"{build_output_language_instruction(preferred_locale, style='json')}"
        )
        if ocr_text.strip():
            prompt += f"\n\n已通过本地 OCR 识别到部分文字，可作为辅助参考：\n{ocr_text[:4000]}"
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
            **self.completion_options,
        )
        raw = response.choices[0].message.content or "{}"
        usage = read_response_usage(response)
        if usage:
            await record_api_usage(self.model, *usage)
        else:
            await record_api_usage(
                self.model,
                prompt_tokens=estimate_tokens(prompt),
                completion_tokens=estimate_tokens(raw),
            )
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            parsed = {}
        return parsed if isinstance(parsed, dict) else {}
