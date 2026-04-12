from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from sqlalchemy import func, select

from shared.database import AsyncSessionLocal
from shared.models import ApiUsageORM, SystemConfigORM
from shared.time_utils import now_in_app_timezone_naive

BILLING_CONFIG_KEY = "api_billing"
SUPPORTED_LIMIT_TYPES = {"token", "cost"}
SUPPORTED_CURRENCIES = {"USD", "CNY", "EUR"}

DEFAULT_BILLING_CONFIG: dict[str, Any] = {
    "api_limit_type": "token",
    "api_limit_value": 0,
    "currency": "USD",
}

USD_TO_CURRENCY = {
    "USD": 1.0,
    "CNY": 7.25,
    "EUR": 0.92,
}

# USD per 1K tokens. This is intentionally small and config-backed later.
MODEL_PRICE_USD_PER_1K = {
    "gpt-4o": {"prompt": 0.005, "completion": 0.015},
    "gpt-4o-mini": {"prompt": 0.00015, "completion": 0.0006},
    "gpt-4.1": {"prompt": 0.002, "completion": 0.008},
    "gpt-4.1-mini": {"prompt": 0.0004, "completion": 0.0016},
    "text-embedding-3-small": {"prompt": 0.00002, "completion": 0.0},
    "text-embedding-3-large": {"prompt": 0.00013, "completion": 0.0},
    "qwen-max": {"prompt": 0.0016, "completion": 0.0064},
    "qwen-plus": {"prompt": 0.0004, "completion": 0.0012},
    "qwen-turbo": {"prompt": 0.00005, "completion": 0.0002},
}


class ApiLimitExceededError(RuntimeError):
    def __init__(self, detail: str):
        self.detail = detail
        super().__init__("API 限额可能已用尽，请联系管理员")


def estimate_tokens(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


def read_response_usage(response: Any) -> tuple[int, int, int] | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None

    prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or (prompt_tokens + completion_tokens))
    if prompt_tokens == 0 and completion_tokens == 0 and total_tokens == 0:
        return None
    return prompt_tokens, completion_tokens, total_tokens


def _normalize_billing_config(value: dict[str, Any] | None) -> dict[str, Any]:
    config = {**DEFAULT_BILLING_CONFIG, **(value or {})}
    if config.get("api_limit_type") not in SUPPORTED_LIMIT_TYPES:
        config["api_limit_type"] = DEFAULT_BILLING_CONFIG["api_limit_type"]
    try:
        config["api_limit_value"] = max(0.0, float(config.get("api_limit_value", 0) or 0))
    except (TypeError, ValueError):
        config["api_limit_value"] = 0.0
    if config.get("currency") not in SUPPORTED_CURRENCIES:
        config["currency"] = DEFAULT_BILLING_CONFIG["currency"]
    return config


def _month_bounds() -> tuple[datetime, datetime]:
    now = now_in_app_timezone_naive()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if start.month == 12:
        end = start.replace(year=start.year + 1, month=1)
    else:
        end = start.replace(month=start.month + 1)
    return start, end


def _price_for_model(model_name: str) -> dict[str, float] | None:
    normalized = (model_name or "").lower()
    for key, price in sorted(MODEL_PRICE_USD_PER_1K.items(), key=lambda item: len(item[0]), reverse=True):
        if key in normalized:
            return price
    return None


async def get_billing_config() -> dict[str, Any]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SystemConfigORM).where(SystemConfigORM.key == BILLING_CONFIG_KEY)
        )
        record = result.scalar_one_or_none()
        return _normalize_billing_config(record.value if record else None)


async def save_billing_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = _normalize_billing_config(payload)
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(
                select(SystemConfigORM).where(SystemConfigORM.key == BILLING_CONFIG_KEY)
            )
            record = result.scalar_one_or_none()
            if record:
                record.value = config
                record.updated_at = now_in_app_timezone_naive()
            else:
                record = SystemConfigORM(key=BILLING_CONFIG_KEY, value=config)
                session.add(record)
    return config


async def get_monthly_usage() -> dict[str, float | int]:
    start, end = _month_bounds()
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(
                func.coalesce(func.sum(ApiUsageORM.total_tokens), 0),
                func.coalesce(func.sum(ApiUsageORM.estimated_cost), 0.0),
            ).where(ApiUsageORM.created_at >= start, ApiUsageORM.created_at < end)
        )
        used_tokens, used_cost = result.one()
        return {
            "used_tokens": int(used_tokens or 0),
            "used_cost": float(used_cost or 0.0),
        }


async def get_billing_state() -> dict[str, Any]:
    config = await get_billing_config()
    usage = await get_monthly_usage()
    limit_type: Literal["token", "cost"] = config["api_limit_type"]
    limit_value = float(config["api_limit_value"])
    used_value = usage["used_tokens"] if limit_type == "token" else usage["used_cost"]
    return {
        **config,
        **usage,
        "limit_exceeded": limit_value > 0 and float(used_value) >= limit_value,
    }


async def check_api_limit_or_raise() -> None:
    state = await get_billing_state()
    limit_value = float(state["api_limit_value"])
    if limit_value <= 0:
        return

    limit_type = state["api_limit_type"]
    used_value = state["used_tokens"] if limit_type == "token" else state["used_cost"]
    if float(used_value) >= limit_value:
        unit = "tokens" if limit_type == "token" else state["currency"]
        raise ApiLimitExceededError(
            f"API monthly {limit_type} limit exceeded: used={used_value}, limit={limit_value} {unit}"
        )


def estimate_cost(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    currency: str,
    force_zero_cost: bool = False,
) -> float:
    if force_zero_cost:
        return 0.0
    price = _price_for_model(model_name)
    if not price:
        return 0.0
    usd_cost = (
        (max(0, prompt_tokens) / 1000.0) * price["prompt"]
        + (max(0, completion_tokens) / 1000.0) * price["completion"]
    )
    return round(usd_cost * USD_TO_CURRENCY.get(currency, 1.0), 8)


async def record_api_usage(
    model_name: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int | None = None,
    estimated_cost: float | None = None,
    force_zero_cost: bool = False,
) -> None:
    total = int(total_tokens if total_tokens is not None else prompt_tokens + completion_tokens)
    config = await get_billing_config()
    cost = (
        float(estimated_cost)
        if estimated_cost is not None
        else estimate_cost(model_name, prompt_tokens, completion_tokens, config["currency"], force_zero_cost)
    )
    async with AsyncSessionLocal() as session:
        async with session.begin():
            session.add(
                ApiUsageORM(
                    model_name=model_name or "unknown",
                    prompt_tokens=max(0, int(prompt_tokens or 0)),
                    completion_tokens=max(0, int(completion_tokens or 0)),
                    total_tokens=max(0, total),
                    estimated_cost=max(0.0, cost),
                )
            )
