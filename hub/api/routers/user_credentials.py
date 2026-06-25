from __future__ import annotations

import json
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from hub.api.schemas import CookieUpsertRequest, UserCredentialResponse, UserCredentialUpsertRequest
from hub.core.security import get_current_user
from shared.constants import PLATFORM_WHITELIST
from shared.credentials import (
    _is_cookie_file_platform,
    build_credential_response_payload,
    detect_cookie_format,
    list_user_credentials,
    parse_cookie_string,
    parse_netscape_to_dict,
    upsert_user_credential,
    validate_platform,
)
from shared.crypto import encrypt_value
from shared.database import AsyncSessionLocal
from shared.models import UserCredentialORM


router = APIRouter(prefix="/api/user/credentials", tags=["User Credentials"])


@router.get("/cookie-platforms")
async def list_cookie_platforms():
    """Return cookie-capable platforms with their domain patterns (public, no auth)."""
    platforms = []
    for platform, meta in PLATFORM_WHITELIST.items():
        if meta.get("credential_kind") == "cookie_file":
            platforms.append({
                "platform": platform,
                "label": meta["label"],
                "domain_patterns": meta.get("domain_patterns", []),
            })
    return platforms


@router.get("/cookie-extension/download")
async def download_cookie_extension(background_tasks: BackgroundTasks):
    """Download the Chrome extension zip for cookie auto-sync."""
    extension_dir = Path(__file__).resolve().parents[3] / "shared" / "chrome_extension"
    if not extension_dir.is_dir():
        raise HTTPException(status_code=404, detail="Chrome extension not found.")

    tmp_dir = tempfile.mkdtemp()
    archive_base = str(Path(tmp_dir) / "pekno-cookie-extension")
    archive_path = shutil.make_archive(base_name=archive_base, format="zip", root_dir=str(extension_dir))
    background_tasks.add_task(shutil.rmtree, tmp_dir, ignore_errors=True)

    return FileResponse(
        archive_path,
        media_type="application/zip",
        filename="pekno-cookie-extension.zip",
    )


@router.get("", response_model=list[UserCredentialResponse])
async def get_user_credentials(current_user=Depends(get_current_user)):
    credentials = await list_user_credentials(current_user["id"])
    return [build_credential_response_payload(credential) for credential in credentials]


@router.post("", response_model=UserCredentialResponse)
@router.put("", response_model=UserCredentialResponse)
async def save_user_credential(payload: UserCredentialUpsertRequest, current_user=Depends(get_current_user)):
    _require_credential_scope(current_user)
    credential = await upsert_user_credential(current_user["id"], payload.platform, payload.token_value)
    return build_credential_response_payload(credential)


def _require_credential_scope(current_user: dict) -> None:
    scopes = current_user.get("scopes") or []
    if scopes and "write:credential" not in scopes:
        raise HTTPException(status_code=403, detail="PAT scope 'write:credential' is required.")


@router.put("/cookie", response_model=UserCredentialResponse)
async def save_cookie_credential(payload: CookieUpsertRequest, current_user=Depends(get_current_user)):
    """Save a cookie credential (auto-detects cookie string or Netscape file format)."""
    _require_credential_scope(current_user)
    validated = validate_platform(payload.platform)
    if not _is_cookie_file_platform(validated):
        raise HTTPException(
            status_code=400,
            detail=f"Platform '{validated}' does not support cookie credentials.",
        )

    raw_input = payload.cookie_value.strip()
    if not raw_input:
        raise HTTPException(status_code=400, detail="Cookie value cannot be empty.")

    # Auto-detect format and validate
    fmt = detect_cookie_format(raw_input)
    if fmt == "netscape_file":
        cookie_dict = parse_netscape_to_dict(raw_input)
    else:
        cookie_dict = parse_cookie_string(raw_input)

    if not cookie_dict:
        raise HTTPException(
            status_code=400,
            detail="No valid cookie fields found in the input.",
        )

    # Store as JSON with format indicator
    storage_payload = json.dumps({"format": fmt, "value": raw_input})
    encrypted_value = encrypt_value(storage_payload)

    from shared.time_utils import now_in_app_timezone_naive

    user_id = current_user["id"]
    async with AsyncSessionLocal() as session:
        async with session.begin():
            from sqlalchemy.dialects.postgresql import insert as pg_insert
            stmt = pg_insert(UserCredentialORM).values(
                user_id=user_id,
                platform=validated,
                token_value=encrypted_value,
            ).on_conflict_do_update(
                index_elements=["user_id", "platform"],
                set_={"token_value": encrypted_value, "updated_at": now_in_app_timezone_naive()},
            )
            await session.execute(stmt)

        from sqlalchemy import select
        result = await session.execute(
            select(UserCredentialORM).where(
                UserCredentialORM.user_id == user_id,
                UserCredentialORM.platform == validated,
            )
        )
        credential = result.scalar_one()
        credential.token_value = raw_input  # For response building

    return build_credential_response_payload(credential)
