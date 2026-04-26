from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from shared.api_errors import ApiError
from shared.constants import PLATFORM_WHITELIST
from shared.crypto import decrypt_value, encrypt_value
from shared.database import AsyncSessionLocal
from shared.error_codes import ERR_CREDENTIAL_UNREADABLE, ERR_INVALID_INPUT
from shared.models import UserCredentialORM


def validate_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    if normalized not in PLATFORM_WHITELIST:
        raise ApiError(
            ERR_INVALID_INPUT,
            f"Unsupported credential platform: {platform}",
            status_code=400,
        )
    return normalized


def validate_required_credentials(required_credentials: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for platform in required_credentials or []:
        validated = validate_platform(platform)
        if validated not in normalized:
            normalized.append(validated)
    return normalized


def mask_credential(token_value: str | None) -> str | None:
    if not token_value:
        return None
    value = token_value.strip()
    if len(value) <= 8:
        return "*" * len(value)
    return f"{value[:4]}***{value[-3:]}"


def _decrypt_token_value(raw_value: str | None) -> str:
    value = raw_value or ""
    decrypted = decrypt_value(value)
    if decrypted is None:
        raise ApiError(
            ERR_CREDENTIAL_UNREADABLE,
            "The stored credential cannot be decrypted. Please re-enter it.",
            status_code=400,
        )
    return decrypted


def _resolve_token_value(raw_value: str | None) -> str:
    value = (raw_value or "").strip()
    if not value:
        return ""
    # Response builders may receive either an encrypted DB value or an already
    # decrypted/plaintext value from upstream helpers.
    if value.startswith("gAAAAA"):
        return _decrypt_token_value(value)
    return value


async def list_user_credentials(user_id: str) -> list[UserCredentialORM]:
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserCredentialORM)
            .where(UserCredentialORM.user_id == user_id)
            .order_by(UserCredentialORM.platform.asc())
        )
        credentials = list(result.scalars().all())
        for credential in credentials:
            credential.token_value = _decrypt_token_value(credential.token_value)
        return credentials


async def get_user_credential(user_id: str, platform: str) -> UserCredentialORM | None:
    normalized = validate_platform(platform)
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserCredentialORM).where(
                UserCredentialORM.user_id == user_id,
                UserCredentialORM.platform == normalized,
            )
        )
        credential = result.scalar_one_or_none()
        if credential:
            credential.token_value = _decrypt_token_value(credential.token_value)
        return credential


async def upsert_user_credential(user_id: str, platform: str, token_value: str) -> UserCredentialORM:
    normalized = validate_platform(platform)
    sanitized = (token_value or "").strip()
    if not sanitized:
        raise ApiError(ERR_INVALID_INPUT, "Credential value cannot be empty.", status_code=400)

    encrypted_value = encrypt_value(sanitized)

    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = insert(UserCredentialORM).values(
                user_id=user_id,
                platform=normalized,
                token_value=encrypted_value,
            ).on_conflict_do_update(
                index_elements=["user_id", "platform"],
                set_={"token_value": encrypted_value},
            )
            await session.execute(stmt)

        result = await session.execute(
            select(UserCredentialORM).where(
                UserCredentialORM.user_id == user_id,
                UserCredentialORM.platform == normalized,
            )
        )
        credential = result.scalar_one()
        credential.token_value = sanitized
        return credential


def build_credential_response_payload(credential: UserCredentialORM) -> dict[str, Any]:
    meta = PLATFORM_WHITELIST[credential.platform]
    token_value = _resolve_token_value(credential.token_value)
    return {
        "id": credential.id,
        "platform": credential.platform,
        "label": meta["label"],
        "masked_value": mask_credential(token_value),
        "created_at": credential.created_at,
        "updated_at": credential.updated_at,
    }


def _is_cookie_file_platform(platform: str) -> bool:
    meta = PLATFORM_WHITELIST.get(platform, {})
    return meta.get("credential_kind") == "cookie_file"


def get_cookie_storage_dir(user_id: str, platform: str) -> "Path":
    from pathlib import Path
    validated = validate_platform(platform)
    meta = PLATFORM_WHITELIST[validated]
    cookie_dir = meta.get("cookie_dir", validated)
    return Path("data") / "cookies" / user_id / cookie_dir


def get_cookie_file_path(user_id: str, platform: str) -> "Path":
    return get_cookie_storage_dir(user_id, platform) / "cookies.txt"


def parse_netscape_cookie_file(file_path: "Path") -> dict[str, str]:
    cookies: dict[str, str] = {}
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 7:
                name, value = parts[5], parts[6]
                cookies[name] = value
    return cookies


def validate_cookie_file(platform: str, file_path: "Path") -> dict[str, Any]:
    import os
    from datetime import datetime

    validated = validate_platform(platform)
    meta = PLATFORM_WHITELIST[validated]
    required_keys = list(meta.get("required_cookie_keys", []))

    result = {
        "platform": validated,
        "file_exists": False,
        "file_date": None,
        "found_keys": [],
        "missing_keys": [],
        "valid": False,
    }

    if not file_path.exists():
        return result

    result["file_exists"] = True
    try:
        mtime = os.path.getmtime(str(file_path))
        result["file_date"] = datetime.fromtimestamp(mtime).isoformat()
    except OSError:
        pass

    try:
        cookies = parse_netscape_cookie_file(file_path)
    except Exception:
        result["missing_keys"] = required_keys
        return result

    for key in required_keys:
        if key in cookies :
            result["found_keys"].append(key)
        else:
            result["missing_keys"].append(key)

    result["valid"] = len(result["missing_keys"]) == 0
    return result


def resolve_cookie_file_path(user_id: str, platform: str) -> str | None:
    import os
    validated = validate_platform(platform)
    meta = PLATFORM_WHITELIST[validated]

    env_var = meta.get("env_var")
    if env_var:
        env_path = os.environ.get(env_var)
        if env_path:
            return env_path

    user_path = get_cookie_file_path(user_id, platform)
    if user_path.exists():
        return str(user_path)

    return None
