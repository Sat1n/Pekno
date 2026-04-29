import asyncio
import gc
import os
import time
from pathlib import Path
from typing import Any

from faster_whisper import WhisperModel
from hub.core.billing import estimate_tokens, record_api_usage
from hub.core.llm.ollama_manager import force_unload_ollama
from shared.logger import worker_log
from worker.runtime import is_cuda_execution_mode


async def _record_whisper_usage(model_name: str, transcript_text: str = "") -> None:
    try:
        tokens = estimate_tokens(transcript_text)
        await record_api_usage(
            model_name=f"whisper:{model_name}",
            prompt_tokens=0,
            completion_tokens=tokens,
            total_tokens=tokens,
            force_zero_cost=True,
        )
    except Exception as exc:
        worker_log.warning("Failed to record Whisper usage: %s", exc)

async def resolve_huggingface_env():
    """Resolve and inject Hugging Face environment settings for downloads."""
    os.environ["HF_HOME"] = str(Path("data") / "cache" / "huggingface")

    os.environ.pop("HF_ENDPOINT", None)
    os.environ.pop("HUGGINGFACE_HUB_ENDPOINT", None)

    # Xet-based distribution can stall in some environments, so prefer the
    # more stable regular download path for Whisper model pulls.
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"

    try:
        from hub.core.model_settings import _load_json_config, _provider_config_key
        hf_config = await _load_json_config(_provider_config_key("huggingface"), {})
        token = hf_config.get("api_key")
        endpoint = str(hf_config.get("endpoint") or "").strip()
        if token and str(token).strip():
            os.environ["HF_TOKEN"] = str(token).strip()
            worker_log.info("Injected Hugging Face access token from provider settings.")
        if endpoint:
            os.environ["HF_ENDPOINT"] = endpoint
            os.environ["HUGGINGFACE_HUB_ENDPOINT"] = endpoint
            worker_log.info("Using custom Hugging Face endpoint: %s", endpoint)
            return
    except Exception as e:
        worker_log.warning("Failed to read Hugging Face provider settings: %s", e)

    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.head("https://huggingface.co", follow_redirects=True)
            if resp.status_code == 200:
                worker_log.info("Hugging Face primary endpoint is reachable; using direct access.")
                return
    except Exception:
        pass

    worker_log.warning(
        "Hugging Face primary endpoint is unavailable; switching to hf-mirror.com."
    )
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    os.environ["HUGGINGFACE_HUB_ENDPOINT"] = "https://hf-mirror.com"


LOW_CONFIDENCE_LANGUAGE_THRESHOLD = 0.55

_model_cache: dict[str, tuple[WhisperModel, str, float]] = {}
IDLE_UNLOAD_SECONDS = 1800


def _free_cuda_vram():
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            worker_log.info("🧹 CUDA VRAM cache cleared via torch.")
    except ImportError:
        pass


async def _cleanup_idle_models(now: float):
    stale = [
        (k, dev) for k, (_, dev, t) in _model_cache.items()
        if now - t > IDLE_UNLOAD_SECONDS
    ]
    if not stale:
        return

    had_cuda = False
    for key, device in stale:
        worker_log.info("🗑️ Unloading idle Whisper model: %s", key)
        del _model_cache[key]
        if device == "cuda":
            had_cuda = True

    gc.collect()
    if had_cuda:
        _free_cuda_vram()


async def _get_or_load_whisper_model(model_name: str, device: str) -> WhisperModel:
    cache_key = f"{model_name}:{device}"
    now = time.time()

    await _cleanup_idle_models(now)

    if cache_key in _model_cache:
        model, _, _ = _model_cache[cache_key]
        _model_cache[cache_key] = (model, device, now)
        return model

    worker_log.info("📦 Loading Whisper model: %s on %s...", model_name, device)
    model = await asyncio.to_thread(
        WhisperModel, model_name, device=device, compute_type="int8"
    )
    _model_cache[cache_key] = (model, device, now)
    worker_log.info("✅ Whisper model loaded: %s", cache_key)
    return model


class TranscriberFactory:
    @staticmethod
    async def transcribe_audio(audio_path: str, provider: str = "local_whisper", model_name: str = "small"):
        """Transcribe audio with the configured speech-to-text provider."""
        if provider == "local_whisper":
            use_cuda = is_cuda_execution_mode()
            if use_cuda:
                worker_log.info("CUDA execution mode detected. Releasing Ollama VRAM before Whisper transcription.")
                await force_unload_ollama()
                await asyncio.sleep(2)
            try:
                await resolve_huggingface_env()

                current_endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
                disable_xet = os.environ.get("HF_HUB_DISABLE_XET", "0")

                if use_cuda:
                    worker_log.info("Loading Faster-Whisper (%s) on CUDA...", model_name)
                    worker_log.info(
                        "Current Hugging Face download environment: endpoint=%s | disable_xet=%s",
                        current_endpoint,
                        disable_xet,
                    )
                    model = await _get_or_load_whisper_model(model_name, "cuda")
                    worker_log.info("Faster-Whisper (%s) loaded successfully on GPU.", model_name)
                else:
                    worker_log.info("CPU execution mode detected. Loading Faster-Whisper (%s) on CPU.", model_name)
                    worker_log.info(
                        "Current Hugging Face download environment: endpoint=%s | disable_xet=%s",
                        current_endpoint,
                        disable_xet,
                    )
                    model = await _get_or_load_whisper_model(model_name, "cpu")
            except Exception as e:
                if not use_cuda:
                    raise
                worker_log.error("Whisper failed to load on GPU: %s", str(e))
                worker_log.warning(
                    "Falling back to CPU transcription. Performance may be significantly slower."
                )
                worker_log.info(
                    "Hugging Face environment before CPU fallback: endpoint=%s | disable_xet=%s",
                    os.environ.get("HF_ENDPOINT", "https://huggingface.co"),
                    os.environ.get("HF_HUB_DISABLE_XET", "0"),
                )
                model = await _get_or_load_whisper_model(model_name, "cpu")

            worker_log.info("Starting local transcription: %s", audio_path)
            segments_generator, info = await asyncio.to_thread(model.transcribe, audio_path, beam_size=5)

            language = getattr(info, "language", None)
            language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
            if language:
                worker_log.info(
                    "Whisper detected language: %s (probability=%.2f)",
                    language,
                    language_probability,
                )

            if language_probability < LOW_CONFIDENCE_LANGUAGE_THRESHOLD:
                worker_log.warning(
                    "Whisper language confidence is too low; skipping segment generation "
                    "(threshold=%.2f). The source may be music, ambient audio, or otherwise "
                    "not reliably transcribable.",
                    LOW_CONFIDENCE_LANGUAGE_THRESHOLD,
                )
                close_fn = getattr(segments_generator, "close", None)
                if callable(close_fn):
                    try:
                        close_fn()
                    except Exception:
                        pass
                await _record_whisper_usage(model_name, "")
                return {
                    "segments": [],
                    "language": language,
                    "language_probability": language_probability,
                    "low_confidence": True,
                }

            result = []
            for s in await asyncio.to_thread(list, segments_generator):
                result.append({
                    "start": s.start,
                    "end": s.end,
                    "text": s.text.strip()
                })
            await _record_whisper_usage(model_name, "\n".join(item["text"] for item in result))
            return {
                "segments": result,
                "language": language,
                "language_probability": language_probability,
                "low_confidence": False,
            }
        else:
            worker_log.info("API transcription route is not implemented yet: %s", provider)
            return {
                "segments": [],
                "language": None,
                "language_probability": 0.0,
                "low_confidence": False,
            }
