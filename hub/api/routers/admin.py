import secrets

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
import tempfile
import subprocess
import os

from hub.api.schemas import (
    BillingSettingsRequest,
    BillingSettingsResponse,
    InvitationCodeResponse,
    InvitationCreateResponse,
)
from hub.core.billing import get_billing_state, save_billing_config
from hub.core import model_settings
from hub.core.security import require_admin
from shared.database import AsyncSessionLocal, DB_USER, DB_PASS, DB_HOST, DB_PORT, DB_NAME
from shared.models import InvitationCodeORM, UserORM, SystemConfigORM

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _generate_invite_code() -> str:
    return f"PEKNO-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"


@router.post("/invitations", response_model=InvitationCreateResponse)
async def create_invitation(current_user=Depends(require_admin)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            code = _generate_invite_code()
            while True:
                existing = await session.execute(
                    select(InvitationCodeORM).where(InvitationCodeORM.code == code)
                )
                if existing.scalar_one_or_none() is None:
                    break
                code = _generate_invite_code()

            invitation = InvitationCodeORM(code=code)
            session.add(invitation)
            await session.flush()

    return InvitationCreateResponse(
        id=invitation.id,
        code=invitation.code,
        is_used=invitation.is_used,
        created_at=invitation.created_at,
    )


@router.get("/invitations", response_model=list[InvitationCodeResponse])
async def list_invitations(current_user=Depends(require_admin)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(InvitationCodeORM, UserORM.username)
            .outerjoin(UserORM, InvitationCodeORM.used_by_user_id == UserORM.id)
            .order_by(InvitationCodeORM.created_at.desc())
        )
        rows = result.all()

    return [
        InvitationCodeResponse(
            id=invitation.id,
            code=invitation.code,
            is_used=invitation.is_used,
            used_by_username=username,
            created_at=invitation.created_at,
        )
        for invitation, username in rows
    ]


@router.get("/models/providers")
async def get_model_providers(current_user=Depends(require_admin)):
    return await model_settings.get_model_provider_state()


@router.put("/models/providers/{provider_id}")
async def update_model_provider(provider_id: str, payload: dict, current_user=Depends(require_admin)):
    try:
        return await model_settings.save_model_provider_config(provider_id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/models/assignments")
async def get_model_assignments(current_user=Depends(require_admin)):
    return {"assignments": await model_settings.get_model_assignments()}


@router.put("/models/assignments")
async def update_model_assignments(payload: dict, current_user=Depends(require_admin)):
    assignments = payload.get("assignments")
    if not isinstance(assignments, list):
        raise HTTPException(status_code=400, detail="assignments 必须为数组")
    try:
        return {"assignments": await model_settings.save_model_assignments(assignments)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/system/billing", response_model=BillingSettingsResponse)
async def get_system_billing(current_user=Depends(require_admin)):
    return await get_billing_state()


@router.put("/system/billing", response_model=BillingSettingsResponse)
async def update_system_billing(payload: BillingSettingsRequest, current_user=Depends(require_admin)):
    await save_billing_config(payload.model_dump())
    return await get_billing_state()


@router.get("/system/developer")
async def get_developer_settings(current_user=Depends(require_admin)):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(SystemConfigORM.value).where(SystemConfigORM.key == "developer_settings")
        )
        val = result.scalar_one_or_none()
        return val or {"pause_scheduler": False}


@router.put("/system/developer")
async def update_developer_settings(payload: dict, current_user=Depends(require_admin)):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            stmt = insert(SystemConfigORM).values(
                key="developer_settings", value=payload
            ).on_conflict_do_update(
                index_elements=["key"],
                set_={"value": payload}
            )
            await session.execute(stmt)
        return payload


@router.get("/system/developer/export")
async def export_database(current_user=Depends(require_admin)):
    db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    fd, path = tempfile.mkstemp(suffix=".dump")
    os.close(fd)
    try:
        subprocess.run(
            ["pg_dump", "-F", "c", "-O", "-x", "-f", path, db_url],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Export failed: {e.stderr.decode('utf-8', errors='replace')}")
    
    return FileResponse(
        path, 
        media_type="application/octet-stream", 
        filename="pekno_database.dump",
        background=BackgroundTask(os.remove, path)
    )


@router.post("/system/developer/import")
async def import_database(file: UploadFile = File(...), current_user=Depends(require_admin)):
    db_url = f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
    fd, path = tempfile.mkstemp(suffix=".dump")
    os.close(fd)
    
    try:
        content = await file.read()
        with open(path, "wb") as f:
            f.write(content)
            
        subprocess.run(
            ["pg_restore", "--clean", "--if-exists", "-O", "-x", "-d", db_url, path],
            check=True,
            capture_output=True,
        )
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Import failed: {e.stderr.decode('utf-8', errors='replace')}")
    finally:
        if os.path.exists(path):
            os.remove(path)
            
    return {"status": "success"}
