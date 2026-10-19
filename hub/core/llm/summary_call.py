"""Bound summary requests and report safe diagnostics without response bodies."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any

import openai

from shared.ai_validation import validate_summary
from shared.api_errors import ApiError
from shared.error_codes import ERR_AI_TIMEOUT, ERR_AI_UNAVAILABLE
from shared.logger import hub_log
from hub.core.llm.providers.openai_client import SUMMARY_TOTAL_TIMEOUT_SECONDS


async def request_summary(
    request: Callable[[], Awaitable[Any]], *, model: str, purpose: str,
    record_usage: Callable[[Any, str], Awaitable[None]],
) -> tuple[Any, str]:
    started = time.monotonic()
    finish_reason = None
    outcome = "failed"
    error_code = None
    exception_type = None
    try:
        async with asyncio.timeout(SUMMARY_TOTAL_TIMEOUT_SECONDS):
            response = await request()
            choice = response.choices[0] if response.choices else None
            finish_reason = getattr(choice, "finish_reason", None)
            raw_content = choice.message.content if choice else None
            # A charged upstream response still counts even if its final body is empty.
            await record_usage(response, raw_content if isinstance(raw_content, str) else "")
            content = validate_summary(raw_content)
            outcome = "completed"
            return response, content
    except (TimeoutError, openai.APITimeoutError) as exc:
        exception_type = type(exc).__name__
        error_code = ERR_AI_TIMEOUT
        raise ApiError(error_code, "The summary request exceeded its time limit.", status_code=504) from None
    except openai.APIError as exc:
        exception_type = type(exc).__name__
        error_code = ERR_AI_UNAVAILABLE
        # Upstream messages may contain keys, input or complete response bodies.
        raise ApiError(error_code, "The summary service request failed.", status_code=502) from None
    except ApiError as exc:
        error_code = exc.error_code
        raise
    finally:
        hub_log.info(
            "model_summary task=%s model=%s elapsed_seconds=%.3f finish_reason=%s "
            "outcome=%s error_code=%s exception_type=%s",
            purpose, model, time.monotonic() - started,
            str(finish_reason)[:64] if finish_reason is not None else None,
            outcome, error_code, exception_type,
        )
