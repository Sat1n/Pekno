import asyncio
import base64
import json
import re
from typing import Any, Dict, List, Tuple

import openai
from langchain_ollama import OllamaEmbeddings

from shared.config import SYSTEM_CONFIG_USER_ID, ConfigManager, get_default_ollama_base_url
from hub.core.llm.providers.ollama_adapter import OllamaProvider, ensure_ollama_model
from hub.core.llm.providers.openai_adapter import OpenAIProvider
from hub.core.billing import check_api_limit_or_raise, estimate_tokens, read_response_usage, record_api_usage

MODEL_SETTINGS_NAMESPACE = "__model_settings__"

MODEL_PROVIDER_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "paddleocr_v5_cpu",
        "name": "PaddleOCR v5 (CPU)",
        "description": "Local CPU-based OCR engine for image text extraction and scanned PDF processing.",
        "badge": "Local OCR",
        "capabilities": ["OCR"],
        "config_fields": [
            {"key": "enabled", "label": "启用 OCR", "type": "string", "default": "true"},
            {"key": "lang", "label": "语言", "type": "string", "default": "ch"},
            {"key": "max_workers", "label": "并发数", "type": "string", "default": "1"},
        ],
    },
    {
        "id": "local_whisper",
        "name": "Local (Faster-Whisper)",
        "description": "High-performance local speech-to-text engine based on CTranslate2, optimized for offline use.",
        "badge": "Local Preferred",
        "capabilities": ["Speech"],
        "config_fields": [],
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "description": "Connect to local or LAN Ollama for offline inference and self-hosted deployments.",
        "badge": "Local Preferred",
        "capabilities": ["LLM", "Embedding", "Vision"],
        "config_fields": [
            {"key": "host", "label": "Service Address", "type": "string", "default": get_default_ollama_base_url()},
        ],
    },
    {
        "id": "openai_compatible",
        "name": "OpenAI Compatible",
        "description": "兼容 OpenAI API 的通用提供商，适配 LM Studio、vLLM、One API 等。",
        "badge": "通用兼容",
        "capabilities": ["LLM", "Embedding", "Vision"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://api.openai.com/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "openai",
        "name": "OpenAI",
        "description": "OpenAI 官方服务，适合 GPT 与 text-embedding 系列模型。",
        "badge": "官方",
        "capabilities": ["LLM", "Embedding", "Vision"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://api.openai.com/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "openrouter",
        "name": "OpenRouter",
        "description": "统一访问多家模型供应商，适合快速试用不同模型。",
        "badge": "聚合",
        "capabilities": ["LLM", "Embedding", "Vision"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://openrouter.ai/api/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "siliconflow",
        "name": "硅基流动",
        "description": "常见国产推理平台，适合接入通用 OpenAI 兼容模型接口。",
        "badge": "国产",
        "capabilities": ["LLM", "Embedding", "Vision"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://api.siliconflow.cn/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "deepseek",
        "name": "DeepSeek",
        "description": "适合代码与通用推理任务，可通过 OpenAI 兼容接口快速接入。",
        "badge": "推理优先",
        "capabilities": ["LLM"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://api.deepseek.com/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "groq",
        "name": "Groq",
        "description": "主打极低延迟，适合作为标签提取和短总结的高速模型提供商。",
        "badge": "低延迟",
        "capabilities": ["LLM"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://api.groq.com/openai/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "together",
        "name": "Together AI",
        "description": "适合多种开源模型托管，方便尝试不同家族的文本与向量模型。",
        "badge": "开源生态",
        "capabilities": ["LLM", "Embedding", "Vision"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://api.together.xyz/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "dashscope",
        "name": "DashScope (Qwen)",
        "description": "Alibaba Cloud model service suitable for text, multimodal, speech, and future video workflows.",
        "badge": "Multimodal Ready",
        "capabilities": ["LLM", "Speech", "Vision", "Video"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://dashscope.aliyuncs.com/compatible-mode/v1"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "zhipu",
        "name": "智谱 AI",
        "description": "国产模型平台，适合后续接入视觉理解与视频理解能力。",
        "badge": "国产多模态",
        "capabilities": ["LLM", "Vision", "Video"],
        "config_fields": [
            {"key": "base_url", "label": "Base URL", "type": "string", "default": "https://open.bigmodel.cn/api/paas/v4"},
            {"key": "api_key", "label": "API Key", "type": "string", "secret": True, "default": ""},
        ],
    },
    {
        "id": "huggingface",
        "name": "Hugging Face",
        "description": "全球最大开源AI社区，提供海量模型。配置 Access Token 可以在下载 Whisper 等重量级模型时解除频率限制并极大获得加速体验。",
        "badge": "开源生态",
        "capabilities": ["Speech", "Vision"],
        "config_fields": [
            {"key": "api_key", "label": "HF Access Token", "type": "string", "secret": True, "default": ""},
            {"key": "endpoint", "label": "下载镜像 / Endpoint", "type": "string", "default": ""},
        ],
    },
]

MODEL_ASSIGNMENT_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "key": "tagging",
        "label": "标签提取模型",
        "description": "负责为内容生成关键词标签。",
        "group": "当前工作流",
        "status": "active",
        "task_type": "llm",
        "default_provider": "",
        "default_model": "",
    },
    {
        "key": "short_summary",
        "label": "短总结模型",
        "description": "负责生成信息流卡片上的短摘要。",
        "group": "当前工作流",
        "status": "active",
        "task_type": "llm",
        "default_provider": "",
        "default_model": "",
    },
    {
        "key": "long_summary",
        "label": "长总结模型",
        "description": "负责生成详细的 AI Markdown 总结。",
        "group": "当前工作流",
        "status": "active",
        "task_type": "llm",
        "default_provider": "",
        "default_model": "",
    },
    {
        "key": "embedding",
        "label": "向量模型",
        "description": "负责全文向量化，用于语义检索与相似度匹配。",
        "group": "当前工作流",
        "status": "active",
        "task_type": "embedding",
        "default_provider": "",
        "default_model": "",
    },
    {
        "key": "ocr",
        "label": "OCR 文字识别引擎",
        "description": "负责图片文字提取与扫描版 PDF 的后台文字识别。",
        "group": "核心多模态",
        "status": "active",
        "task_type": "ocr",
        "default_provider": "paddleocr_v5_cpu",
        "default_model": "PP-OCRv5",
    },
    {
        "key": "speech_to_text",
        "label": "语音转文字引擎",
        "description": "为后续视频音轨抽取与播客内容处理预留，将语音内容转换为可检索文本。",
        "group": "核心多模态",
        "status": "active",
        "task_type": "speech",
        "default_provider": "local_whisper",
        "default_model": "small",
    },
    {
        "key": "image_understanding",
        "label": "图片语义理解引擎",
        "description": "为封面图、截图和图文内容提取语义信息预留，后续可用于图像标签与摘要。",
        "group": "核心多模态",
        "status": "active",
        "task_type": "vision",
        "default_provider": "zhipu",
        "default_model": "glm-4v-plus",
    },
    {
        "key": "video_understanding",
        "label": "视频理解引擎",
        "description": "为后续视频内容理解、片段总结与时间轴摘要预留。",
        "group": "多模态占位",
        "status": "planned",
        "task_type": "video",
        "default_provider": "dashscope",
        "default_model": "qwen-vl-max",
    },
]


def _is_provider_configured(provider_id: str, config: Dict[str, Any], is_configured_in_db: bool) -> bool:
    if provider_id == "local_whisper":
        return True

    if provider_id == "paddleocr_v5_cpu":
        return str(config.get("enabled", "true")).strip().lower() not in {"false", "0", "no", "off"}

    api_key = config.get("api_key")
    if isinstance(api_key, str):
        return bool(api_key)

    host = config.get("host")
    if isinstance(host, str):
        return bool(host)

    return is_configured_in_db


def _normalize_ollama_host(host: str) -> str:
    normalized = (host or get_default_ollama_base_url()).rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized


def parse_tag_list(raw_text: str) -> List[str]:
    parts = re.split(r"[,，\n]+", raw_text or "")
    cleaned: List[str] = []
    for part in parts:
        tag = part.strip().strip("#")
        if not tag or tag in cleaned:
            continue
        cleaned.append(tag)
    return cleaned[:8]


def _provider_config_key(provider_id: str) -> str:
    return f"provider_config::{provider_id}"


def _assignment_key(purpose: str) -> str:
    return f"assignment::{purpose}"


def _catalog_map() -> Dict[str, Dict[str, Any]]:
    return {provider["id"]: provider for provider in MODEL_PROVIDER_CATALOG}


async def _load_json_config(key: str, default: Dict[str, Any]) -> Dict[str, Any]:
    raw_value = await ConfigManager.get_config(
        MODEL_SETTINGS_NAMESPACE,
        key,
        default=None,
        user_id=SYSTEM_CONFIG_USER_ID,
    )
    if not raw_value:
        return dict(default)
    try:
        parsed = json.loads(raw_value)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    return dict(default)


async def _save_json_config(key: str, value: Dict[str, Any], description: str) -> bool:
    return await ConfigManager.set_config(
        MODEL_SETTINGS_NAMESPACE,
        key,
        json.dumps(value, ensure_ascii=True),
        description=description,
        user_id=SYSTEM_CONFIG_USER_ID,
    )


async def get_model_provider_state() -> Dict[str, Any]:
    provider_states: List[Dict[str, Any]] = []
    for provider in MODEL_PROVIDER_CATALOG:
        defaults = {
            field["key"]: field.get("default")
            for field in provider.get("config_fields", [])
        }
        
        raw_value = await ConfigManager.get_config(
            MODEL_SETTINGS_NAMESPACE,
            _provider_config_key(provider["id"]),
            default=None,
            user_id=SYSTEM_CONFIG_USER_ID,
        )
        is_configured_in_db = raw_value is not None
        
        config = await _load_json_config(_provider_config_key(provider["id"]), defaults)
        secret_preview = None
        api_key = config.get("api_key")
        if isinstance(api_key, str) and api_key:
            secret_preview = f"{api_key[:4]}..." if len(api_key) > 4 else api_key
            config["api_key"] = ""
            
        is_configured = _is_provider_configured(provider["id"], config, is_configured_in_db)

        provider_states.append(
            {
                **provider,
                "config": config,
                "is_configured": is_configured,
                "secret_preview": secret_preview,
            }
        )

    assignments = await get_model_assignments()
    return {
        "providers": provider_states,
        "assignments": assignments,
    }


async def save_model_provider_config(provider_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    provider = _catalog_map().get(provider_id)
    if not provider:
        raise ValueError("Unknown model provider.")

    defaults = {
        field["key"]: field.get("default")
        for field in provider.get("config_fields", [])
    }
    current = await _load_json_config(_provider_config_key(provider_id), defaults)

    merged = dict(current)
    for field in provider.get("config_fields", []):
        key = field["key"]
        if key not in payload:
            continue
        value = payload.get(key)
        if field.get("secret") and (value is None or str(value).strip() == ""):
            continue
        merged[key] = value

    success = await _save_json_config(
        _provider_config_key(provider_id),
        merged,
        description=f"模型提供商配置: {provider['name']}",
    )
    if not success:
        raise ValueError("保存模型提供商配置失败")

    return await get_model_provider_state()


async def get_model_assignments() -> List[Dict[str, Any]]:
    assignments: List[Dict[str, Any]] = []
    for item in MODEL_ASSIGNMENT_DEFINITIONS:
        default_value = {
            "provider": item["default_provider"],
            "model": item["default_model"],
        }
        config = await _load_json_config(_assignment_key(item["key"]), default_value)
        assignments.append(
            {
                **item,
                "provider": config.get("provider", item["default_provider"]),
                "model": config.get("model", item["default_model"]),
            }
        )
    return assignments


async def save_model_assignments(assignments: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    definition_map = {item["key"]: item for item in MODEL_ASSIGNMENT_DEFINITIONS}
    capability_map = {
        "llm": "LLM",
        "embedding": "Embedding",
        "speech": "Speech",
        "vision": "Vision",
        "video": "Video",
        "ocr": "OCR",
    }
    validated_payloads: list[tuple[str, dict[str, Any], str]] = []
    for assignment in assignments:
        key = assignment.get("key")
        if key not in definition_map:
            continue
        definition = definition_map[key]
        provider_id = assignment.get("provider", definition["default_provider"])
        if provider_id:
            provider = _catalog_map().get(provider_id)
            if not provider:
                raise ValueError(f"Unknown model provider: {provider_id}")
            required_capability = capability_map.get(definition["task_type"])
            if required_capability and required_capability not in provider.get("capabilities", []):
                raise ValueError(f"Provider [{provider_id}] does not support assignment [{definition['label']}].")
        validated_payloads.append((key, {
            "provider": provider_id,
            "model": assignment.get("model", definition["default_model"]),
        }, f"System model assignment: {definition['label']}"))

    for key, payload, description in validated_payloads:
        success = await _save_json_config(
            _assignment_key(key),
            payload,
            description=description,
        )
        if not success:
            raise ValueError(f"Failed to save model assignment: {key}")
    return await get_model_assignments()


async def _resolve_assignment(purpose: str) -> Dict[str, Any]:
    assignments = await get_model_assignments()
    for assignment in assignments:
        if assignment["key"] == purpose:
            return assignment
    raise ValueError(f"未知模型用途: {purpose}")


async def _build_llm_provider(purpose: str):
    assignment = await _resolve_assignment(purpose)
    provider_id = assignment["provider"]
    model = assignment["model"]
    provider_config = await _load_json_config(_provider_config_key(provider_id), {})

    if provider_id == "ollama":
        return OllamaProvider(_normalize_ollama_host(provider_config.get("host", get_default_ollama_base_url())), model), model

    api_key = provider_config.get("api_key")
    base_url = provider_config.get("base_url", "https://api.openai.com/v1")
    if not api_key:
        raise ValueError(f"Provider [{provider_id}] does not have an API key configured.")
    return OpenAIProvider(api_key=api_key, base_url=base_url, model=model), model


async def generate_summary(text: str, length: str = "short", preferred_locale: str | None = None) -> Tuple[str, str]:
    purpose = "short_summary" if length == "short" else "long_summary"
    provider, model_name = await _build_llm_provider(purpose)
    summary = await provider.generate_summary(text, length=length, preferred_locale=preferred_locale)
    return summary, model_name


async def extract_tags(text: str, preferred_locale: str | None = None) -> Tuple[List[str], str]:
    provider, model_name = await _build_llm_provider("tagging")
    tags = await provider.extract_tags(text, preferred_locale=preferred_locale)
    return tags, model_name


async def embed_text(text: str) -> Tuple[List[float], str]:
    await check_api_limit_or_raise()
    assignment = await _resolve_assignment("embedding")
    provider_id = assignment["provider"]
    model_name = assignment["model"]
    provider_config = await _load_json_config(_provider_config_key(provider_id), {})

    if provider_id == "ollama":
        base_url = _normalize_ollama_host(provider_config.get("host", get_default_ollama_base_url()))
        await ensure_ollama_model(base_url, model_name)
        client = OllamaEmbeddings(
            model=model_name,
            base_url=base_url,
        )
        vector = await asyncio.to_thread(client.embed_query, text)
        await record_api_usage(
            model_name,
            prompt_tokens=estimate_tokens(text),
            completion_tokens=0,
            force_zero_cost=True,
        )
        return vector, model_name

    api_key = provider_config.get("api_key")
    base_url = provider_config.get("base_url", "https://api.openai.com/v1")
    if not api_key:
        raise ValueError(f"Provider [{provider_id}] does not have an API key configured.")

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.embeddings.create(model=model_name, input=text)
    usage = read_response_usage(response)
    if usage:
        await record_api_usage(model_name, *usage)
    else:
        await record_api_usage(model_name, prompt_tokens=estimate_tokens(text), completion_tokens=0)
    return response.data[0].embedding, model_name


def _normalize_image_understanding_result(payload: Dict[str, Any]) -> Dict[str, Any]:
    short_caption = str(
        payload.get("short_caption")
        or payload.get("caption")
        or payload.get("summary")
        or ""
    ).strip()
    detailed_summary = str(
        payload.get("detailed_summary_markdown")
        or payload.get("detailed_summary")
        or payload.get("long_summary")
        or ""
    ).strip()
    ocr_text = str(payload.get("ocr_text") or payload.get("text") or "").strip()
    scene = str(payload.get("scene") or "").strip()

    raw_tags = payload.get("tags") or []
    if isinstance(raw_tags, str):
        tags = parse_tag_list(raw_tags)
    elif isinstance(raw_tags, list):
        tags = [str(tag).strip() for tag in raw_tags if str(tag).strip()][:12]
    else:
        tags = []

    raw_objects = payload.get("objects") or []
    if isinstance(raw_objects, str):
        objects = parse_tag_list(raw_objects)
    elif isinstance(raw_objects, list):
        objects = [str(obj).strip() for obj in raw_objects if str(obj).strip()][:20]
    else:
        objects = []

    if not short_caption and detailed_summary:
        short_caption = detailed_summary.splitlines()[0].strip("# ").strip()[:80]
    if not detailed_summary and short_caption:
        details = [f"This image shows: {short_caption}"]
        if ocr_text:
            details.append(f"## OCR Text\n\n{ocr_text}")
        if objects:
            details.append(f"## Key Objects\n\n- " + "\n- ".join(objects))
        detailed_summary = "\n\n".join(details)

    return {
        "short_caption": short_caption,
        "detailed_summary_markdown": detailed_summary,
        "tags": tags,
        "ocr_text": ocr_text,
        "objects": objects,
        "scene": scene,
    }


async def understand_image(
    image_bytes: bytes,
    mime_type: str,
    ocr_text: str = "",
    preferred_locale: str | None = None,
) -> Tuple[Dict[str, Any], str, str]:
    assignment = await _resolve_assignment("image_understanding")
    provider_id = assignment["provider"]
    provider, model_name = await _build_llm_provider("image_understanding")
    image_data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    raw_result = await provider.understand_image(
        image_data_url,
        ocr_text=ocr_text,
        preferred_locale=preferred_locale,
    )
    normalized = _normalize_image_understanding_result(raw_result)
    return normalized, provider_id, model_name
