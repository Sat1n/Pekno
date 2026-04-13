from __future__ import annotations

from fastapi import APIRouter, Depends

from hub.api.schemas import UserCredentialResponse, UserCredentialUpsertRequest
from hub.core.security import get_current_user
from shared.credentials import (
    build_credential_response_payload,
    list_user_credentials,
    upsert_user_credential,
)


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

