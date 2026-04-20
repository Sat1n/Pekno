import asyncio
import fcntl
import hashlib
import os
import openai
import httpx
from pathlib import Path
from ..base import BaseLLMProvider
import re
import json
from typing import Any
from shared.locale import build_output_language_instruction
from shared.logger import hub_log

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


_pull_locks: dict[tuple[str, str], asyncio.Lock] = {}


def _is_ollama_model_not_found(exc: Exception) -> bool:
    if not isinstance(exc, openai.NotFoundError):
        return False
    message = str(exc).lower()
    return "model" in message and "not found" in message


def _lock_path_for_model(host: str, model: str) -> Path:
    lock_root = Path(os.getenv("PEKNO_LOCK_DIR", "/app/data/locks"))
    try:
        lock_root.mkdir(parents=True, exist_ok=True)
    except Exception:
        lock_root = Path("/tmp")
    digest = hashlib.sha256(f"{host}:{model}".encode("utf-8")).hexdigest()[:24]
    return lock_root / f"ollama-pull-{digest}.lock"


def _acquire_model_pull_file_lock(host: str, model: str):
    lock_file = _lock_path_for_model(host, model)
    handle = lock_file.open("w")
    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


async def _ollama_model_exists(host: str, model: str) -> bool:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(f"{host}/api/show", json={"name": model})
        if response.status_code == 200:
            return True
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True


async def ensure_ollama_model(host: str, model: str) -> None:
    """Pull an Ollama model if it is missing.

    The call is idempotent from Pekno' perspective. Ollama will return quickly
    when the model is already present, and concurrent Pekno tasks share a
    per-process lock to avoid duplicate pulls for the same model.
    """
    model_name = (model or "").strip()
    if not model_name:
        return

    base_host = host.rstrip("/")
    lock_key = (base_host, model_name)
    lock = _pull_locks.setdefault(lock_key, asyncio.Lock())

    async with lock:
        file_lock = await asyncio.to_thread(_acquire_model_pull_file_lock, base_host, model_name)
        try:
            if await _ollama_model_exists(base_host, model_name):
                return

            hub_log.info("Ollama model is missing. Pulling model: %s", model_name)
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.post(
                    f"{base_host}/api/pull",
                    json={"name": model_name, "stream": False},
                )
                response.raise_for_status()
            hub_log.info("Ollama model pull completed: %s", model_name)
        finally:
            fcntl.flock(file_lock.fileno(), fcntl.LOCK_UN)
            file_lock.close()


class OllamaProvider(BaseLLMProvider):
    def __init__(self, host: str, model: str):
        self.host = host.rstrip("/")
        # Ollama 默认 OpenAI 兼容地址通常是 http://localhost:11434/v1
        self.client = openai.AsyncOpenAI(
            api_key="ollama", # Ollama 不需要真正的 Key
            base_url=f"{self.host}/v1"
        )
        self.model_name = model

    async def _create_chat_completion(self, **kwargs: Any):
        try:
            return await self.client.chat.completions.create(**kwargs)
        except Exception as exc:
            if not _is_ollama_model_not_found(exc):
                raise
            await ensure_ollama_model(self.host, self.model_name)
            return await self.client.chat.completions.create(**kwargs)

    async def generate_summary(self, text: str, length: str = "short", preferred_locale: str | None = None) -> str:
        await check_api_limit_or_raise()
        language_instruction = build_output_language_instruction(preferred_locale)
        if length == "short":
            prompt = (
                "请提取这段内容的最核心信息，生成一段30-50字的极简摘要。"
                "必须直接输出摘要结果，不要输出任何如'好的'、'这段内容'之类的解释词汇。\n"
                f"{language_instruction}\n{text[:2000]}"
            )
        else:
            prompt = (
                f"你是一个开源项目分析专家。请根据这段 README 内容详细总结项目的:\n"
                f"1. 核心功能与亮点\n2. 技术架构栈\n3. 简易部署与使用方式\n\n"
                f"{language_instruction}\n"
                f"字数不限，要求排版精美的 Markdown 格式，层级清晰，重点突出：\n{text[:8000]}"
            )
            
        response = await self._create_chat_completion(
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

    async def extract_tags(self, text: str, preferred_locale: str | None = None) -> list[str]:
        await check_api_limit_or_raise()
        prompt = (
            "提取3个关键词，逗号隔开。\n"
            f"{build_output_language_instruction(preferred_locale, style='tags')}\n{text[:500]}"
        )
        response = await self._create_chat_completion(
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

    async def understand_image(self, image_data_url: str, ocr_text: str = "", preferred_locale: str | None = None) -> dict:
        await check_api_limit_or_raise()
        prompt = (
            "你是一个图片理解助手。请分析图片，并只返回 JSON 对象。"
            'JSON schema: {"short_caption": string, "detailed_summary_markdown": string, "tags": string[], '
            '"ocr_text": string, "objects": string[], "scene": string}. '
            "不要输出额外说明。 "
            f"{build_output_language_instruction(preferred_locale, style='json')}"
        )
        if ocr_text.strip():
            prompt += f"\n\n已通过本地 OCR 识别到部分文字，可作为辅助参考：\n{ocr_text[:4000]}"
        response = await self._create_chat_completion(
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
