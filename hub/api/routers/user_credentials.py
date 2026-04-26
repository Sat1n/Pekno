from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from hub.api.schemas import UserCredentialResponse, UserCredentialUpsertRequest
from hub.core.security import get_current_user
from shared.constants import PLATFORM_WHITELIST
from shared.credentials import (
    _is_cookie_file_platform,
    build_credential_response_payload,
    get_cookie_storage_dir,
    list_user_credentials,
    parse_netscape_cookie_file,
    upsert_user_credential,
    validate_cookie_file,
    validate_platform,
)
from shared.error_codes import ERR_INVALID_INPUT


router = APIRouter(prefix="/api/user/credentials", tags=["User Credentials"])


@router.get("", response_model=list[UserCredentialResponse])
async def get_user_credentials(current_user=Depends(get_current_user)):
    credentials = await list_user_credentials(current_user["id"])
    return [build_credential_response_payload(credential) for credential in credentials]


@router.post("", response_model=UserCredentialResponse)
@router.put("", response_model=UserCredentialResponse)
async def save_user_credential(payload: UserCredentialUpsertRequest, current_user=Depends(get_current_user)):
    credential = await upsert_user_credential(current_user["id"], payload.platform, payload.token_value)
    return build_credential_response_payload(credential)


@router.post("/cookie-file")
async def upload_cookie_file(
    platform: str = Form(...),
    file: UploadFile = File(...),
    current_user=Depends(get_current_user),
):
    validated = validate_platform(platform)
    meta = PLATFORM_WHITELIST[validated]
    if not _is_cookie_file_platform(validated):
        raise HTTPException(
            status_code=400,
            detail=f"Platform '{validated}' does not support cookie file upload.",
        )

    if not file.filename or not file.filename.endswith(".txt"):
        raise HTTPException(
            status_code=400,
            detail="Only .txt cookie files (Netscape format) are accepted.",
        )

    content = await file.read()
    if len(content) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Cookie file too large (max 2MB).")

    storage_dir = get_cookie_storage_dir(current_user["id"], validated)
    storage_dir.mkdir(parents=True, exist_ok=True)
    file_path = storage_dir / "cookies.txt"

    with open(file_path, "wb") as f:
        f.write(content)

    validation = validate_cookie_file(validated, file_path)

    return {
        "platform": validated,
        "label": meta["label"],
        "file_date": validation["file_date"],
        "found_keys": validation["found_keys"],
        "missing_keys": validation["missing_keys"],
        "valid": validation["valid"],
        "required_keys": list(meta.get("required_cookie_keys", [])),
    }
