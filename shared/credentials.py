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
