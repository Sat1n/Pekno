import secrets

from fastapi import APIRouter, Depends
from sqlalchemy import select

from hub.api.schemas import InvitationCodeResponse, InvitationCreateResponse
from hub.core.security import require_admin
from shared.database import AsyncSessionLocal
from shared.models import InvitationCodeORM, UserORM

router = APIRouter(prefix="/api/admin", tags=["Admin"])


def _generate_invite_code() -> str:
    return f"IRIS-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"


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
