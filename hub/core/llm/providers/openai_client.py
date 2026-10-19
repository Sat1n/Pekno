"""Shared, explicit authentication for OpenAI-compatible model calls."""

import openai
import httpx

MODEL_REQUEST_TIMEOUT_SECONDS = 120
MODEL_MAX_RETRIES = 1
SUMMARY_TOTAL_TIMEOUT_SECONDS = 180


def create_openai_client(api_key: str | None, base_url: str) -> openai.AsyncOpenAI:
    key = (api_key or "").strip()
    # None would let the SDK read OPENAI_API_KEY from the worker environment.
    # Omit the header explicitly, including with SDK versions that emit Bearer "".
    return openai.AsyncOpenAI(
        api_key=key,
        base_url=base_url,
        default_headers={"Authorization": openai.Omit()} if not key else None,
        timeout=httpx.Timeout(MODEL_REQUEST_TIMEOUT_SECONDS, connect=5),
        max_retries=MODEL_MAX_RETRIES,
    )
