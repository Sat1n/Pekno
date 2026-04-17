import httpx

from hub.core.model_settings import _load_json_config, _provider_config_key
from shared.config import get_default_ollama_base_url
from shared.logger import hub_log


def _normalize_ollama_base_url(base_url: str | None) -> str:
    normalized = (base_url or get_default_ollama_base_url()).strip().rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return normalized


async def _resolve_ollama_base_url(explicit_base_url: str | None = None) -> str:
    if explicit_base_url:
        return _normalize_ollama_base_url(explicit_base_url)

    try:
        config = await _load_json_config(_provider_config_key("ollama"), {})
        return _normalize_ollama_base_url(config.get("host"))
    except Exception as exc:
        hub_log.warning("Failed to resolve Ollama host from model settings: %s", exc)
        return _normalize_ollama_base_url(None)


async def force_unload_ollama(base_url: str | None = None) -> None:
    """
    Ask Ollama to unload all currently resident models so GPU VRAM can be
    reclaimed before another heavy local workload starts.
    """
    resolved_base_url = await _resolve_ollama_base_url(base_url)

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{resolved_base_url}/api/ps")
            response.raise_for_status()
            models = response.json().get("models", [])
            unloaded_any = False

            for model_info in models:
                model_name = model_info.get("name")
                if not model_name:
                    continue
                await client.post(
                    f"{resolved_base_url}/api/generate",
                    json={"model": model_name, "keep_alive": 0},
                )
                hub_log.info("Sent unload signal to Ollama model: %s", model_name)
                unloaded_any = True

            if unloaded_any:
                hub_log.info("Ollama VRAM release request completed.")
            else:
                hub_log.debug("No resident Ollama models were found.")
    except Exception as exc:
        hub_log.warning("Failed to unload Ollama models before GPU task execution: %s", exc)


async def clear_vram_for_whisper(base_url: str | None = None) -> None:
    await force_unload_ollama(base_url)
