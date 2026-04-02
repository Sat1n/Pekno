import asyncio
import base64
import json
import re
from typing import Any, Dict, List, Tuple

import openai
from langchain_ollama import OllamaEmbeddings

from shared.config import SYSTEM_CONFIG_USER_ID, ConfigManager
from hub.core.llm.providers.ollama_adapter import OllamaProvider
from hub.core.llm.providers.openai_adapter import OpenAIProvider

MODEL_SETTINGS_NAMESPACE = "__model_settings__"

MODEL_PROVIDER_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "local_whisper",
        "name": "Local (Faster-Whisper)",
        "description": "本地高性能语音转写引擎，基于 CTranslate2 深度优化，无需网络即可硬解语音流。",
        "badge": "本地优先",
        "capabilities": ["Speech"],
        "config_fields": [],
    },
    {
        "id": "ollama",
        "name": "Ollama",
        "description": "连接本地或局域网 Ollama，适合离线推理与自托管场景。",
        "badge": "本地优先",
        "capabilities": ["LLM", "Embedding", "Vision"],
        "config_fields": [
            {"key": "host", "label": "服务地址", "type": "string", "default": "http://127.0.0.1:11434"},
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
        "name": "通义千问（DashScope）",
        "description": "阿里云模型服务，后续适合接入文本、多模态和语音能力。",
        "badge": "多模态预备",
        "capabilities": ["LLM", "Speech", "Vision"],
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


def _normalize_ollama_host(host: str) -> str:
    normalized = (host or "http://127.0.0.1:11434").rstrip("/")
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
            
        if "api_key" in defaults:
            is_configured = bool(api_key)
        else:
            is_configured = is_configured_in_db and bool(config.get("host"))

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
        raise ValueError("未知模型提供商")

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
    for assignment in assignments:
        key = assignment.get("key")
        if key not in definition_map:
            continue
        definition = definition_map[key]
        payload = {
            "provider": assignment.get("provider", definition["default_provider"]),
            "model": assignment.get("model", definition["default_model"]),
        }
        success = await _save_json_config(
            _assignment_key(key),
            payload,
            description=f"系统模型用途配置: {definition['label']}",
        )
        if not success:
            raise ValueError(f"保存模型用途失败: {key}")
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
        return OllamaProvider(_normalize_ollama_host(provider_config.get("host", "http://127.0.0.1:11434")), model), model

    api_key = provider_config.get("api_key")
    base_url = provider_config.get("base_url", "https://api.openai.com/v1")
    if not api_key:
        raise ValueError(f"模型提供商 [{provider_id}] 尚未配置 API Key")
    return OpenAIProvider(api_key=api_key, base_url=base_url, model=model), model


async def generate_summary(text: str, length: str = "short") -> Tuple[str, str]:
    purpose = "short_summary" if length == "short" else "long_summary"
    provider, model_name = await _build_llm_provider(purpose)
    summary = await provider.generate_summary(text, length=length)
    return summary, model_name


async def extract_tags(text: str) -> Tuple[List[str], str]:
    provider, model_name = await _build_llm_provider("tagging")
    tags = await provider.extract_tags(text)
    return tags, model_name


async def embed_text(text: str) -> Tuple[List[float], str]:
    assignment = await _resolve_assignment("embedding")
    provider_id = assignment["provider"]
    model_name = assignment["model"]
    provider_config = await _load_json_config(_provider_config_key(provider_id), {})

    if provider_id == "ollama":
        client = OllamaEmbeddings(
            model=model_name,
            base_url=_normalize_ollama_host(provider_config.get("host", "http://127.0.0.1:11434")),
        )
        vector = await asyncio.to_thread(client.embed_query, text)
        return vector, model_name

    api_key = provider_config.get("api_key")
    base_url = provider_config.get("base_url", "https://api.openai.com/v1")
    if not api_key:
        raise ValueError(f"模型提供商 [{provider_id}] 尚未配置 API Key")

    client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url)
    response = await client.embeddings.create(model=model_name, input=text)
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
        details = [f"这张图片展示了：{short_caption}"]
        if ocr_text:
            details.append(f"## 图片文字\n\n{ocr_text}")
        if objects:
            details.append(f"## 关键元素\n\n- " + "\n- ".join(objects))
        detailed_summary = "\n\n".join(details)

    return {
        "short_caption": short_caption,
        "detailed_summary_markdown": detailed_summary,
        "tags": tags,
        "ocr_text": ocr_text,
        "objects": objects,
        "scene": scene,
    }


async def understand_image(image_bytes: bytes, mime_type: str) -> Tuple[Dict[str, Any], str, str]:
    assignment = await _resolve_assignment("image_understanding")
    provider_id = assignment["provider"]
    provider, model_name = await _build_llm_provider("image_understanding")
    image_data_url = f"data:{mime_type};base64,{base64.b64encode(image_bytes).decode('ascii')}"
    raw_result = await provider.understand_image(image_data_url)
    normalized = _normalize_image_understanding_result(raw_result)
    return normalized, provider_id, model_name
