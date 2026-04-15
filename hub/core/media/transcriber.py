import asyncio
import os
from typing import Any

from hub.core.billing import estimate_tokens, record_api_usage
from hub.core.llm.ollama_manager import force_unload_ollama
from shared.config import is_cuda_execution_mode
from shared.logger import hub_log


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
        hub_log.warning("Failed to record Whisper usage: %s", exc)

async def resolve_huggingface_env():
    """Resolve and inject Hugging Face environment settings for downloads."""
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
            hub_log.info("Injected Hugging Face access token from provider settings.")
        if endpoint:
            os.environ["HF_ENDPOINT"] = endpoint
            os.environ["HUGGINGFACE_HUB_ENDPOINT"] = endpoint
            hub_log.info("Using custom Hugging Face endpoint: %s", endpoint)
            return
    except Exception as e:
        hub_log.warning("Failed to read Hugging Face provider settings: %s", e)

    import httpx
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.head("https://huggingface.co", follow_redirects=True)
            if resp.status_code == 200:
                hub_log.info("Hugging Face primary endpoint is reachable; using direct access.")
                return
    except Exception:
        pass

    hub_log.warning(
        "Hugging Face primary endpoint is unavailable; switching to hf-mirror.com."
    )
    os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    os.environ["HUGGINGFACE_HUB_ENDPOINT"] = "https://hf-mirror.com"


LOW_CONFIDENCE_LANGUAGE_THRESHOLD = 0.55


class TranscriberFactory:
    @staticmethod
    async def transcribe_audio(audio_path: str, provider: str = "local_whisper", model_name: str = "small"):
        """Transcribe audio with the configured speech-to-text provider."""
        if provider == "local_whisper":
            use_cuda = is_cuda_execution_mode()
            if use_cuda:
                hub_log.info("CUDA execution mode detected. Releasing Ollama VRAM before Whisper transcription.")
                await force_unload_ollama()
                await asyncio.sleep(2)
            try:
                await resolve_huggingface_env()
                
                from faster_whisper import WhisperModel
                current_endpoint = os.environ.get("HF_ENDPOINT", "https://huggingface.co")
                disable_xet = os.environ.get("HF_HUB_DISABLE_XET", "0")

                if use_cuda:
                    hub_log.info("Loading Faster-Whisper (%s) on CUDA...", model_name)
                    hub_log.info(
                        "Current Hugging Face download environment: endpoint=%s | disable_xet=%s",
                        current_endpoint,
                        disable_xet,
                    )
                    model = await asyncio.to_thread(WhisperModel, model_name, device="cuda", compute_type="int8")
                    hub_log.info("Faster-Whisper (%s) loaded successfully on GPU.", model_name)
                else:
                    hub_log.info("CPU execution mode detected. Loading Faster-Whisper (%s) on CPU.", model_name)
                    hub_log.info(
                        "Current Hugging Face download environment: endpoint=%s | disable_xet=%s",
                        current_endpoint,
                        disable_xet,
                    )
                    model = await asyncio.to_thread(WhisperModel, model_name, device="cpu", compute_type="int8")
            except Exception as e:
                if not use_cuda:
                    raise
                hub_log.error("Whisper failed to load on GPU: %s", str(e))
                hub_log.warning(
                    "Falling back to CPU transcription. Performance may be significantly slower."
                )
                hub_log.info(
                    "Hugging Face environment before CPU fallback: endpoint=%s | disable_xet=%s",
                    os.environ.get("HF_ENDPOINT", "https://huggingface.co"),
                    os.environ.get("HF_HUB_DISABLE_XET", "0"),
                )
                model = await asyncio.to_thread(WhisperModel, model_name, device="cpu", compute_type="int8")

            hub_log.info("Starting local transcription: %s", audio_path)
            segments_generator, info = await asyncio.to_thread(model.transcribe, audio_path, beam_size=5)

            language = getattr(info, "language", None)
            language_probability = float(getattr(info, "language_probability", 0.0) or 0.0)
            if language:
                hub_log.info(
                    "Whisper detected language: %s (probability=%.2f)",
                    language,
                    language_probability,
                )

            if language_probability < LOW_CONFIDENCE_LANGUAGE_THRESHOLD:
                hub_log.warning(
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
            hub_log.info("API transcription route is not implemented yet: %s", provider)
            return {
                "segments": [],
                "language": None,
                "language_probability": 0.0,
                "low_confidence": False,
            }
