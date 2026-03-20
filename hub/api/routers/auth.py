from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select

from hub.api.schemas import (
    AuthRegisterRequest,
    AuthInitRequest,
    AuthLoginRequest,
    AuthStatusResponse,
    ChangePasswordRequest,
    TokenResponse,
)
from hub.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_current_user,
    get_password_hash,
    verify_password,
)
from shared.database import AsyncSessionLocal
from shared.models import InvitationCodeORM, UserORM

router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.get("/status", response_model=AuthStatusResponse)
async def auth_status():
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(func.count()).select_from(UserORM))
        user_count = result.scalar_one()

    return AuthStatusResponse(needs_initialization=user_count == 0)


@router.post("/init", response_model=TokenResponse)
async def initialize_super_admin(payload: AuthInitRequest):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            result = await session.execute(select(func.count()).select_from(UserORM))
            user_count = result.scalar_one()
            if user_count > 0:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="系统已初始化，禁止再次创建超级管理员。",
                )

            user = UserORM(
                username=payload.username.strip(),
                hashed_password=get_password_hash(payload.password),
                role="super_admin",
            )
            session.add(user)
            await session.flush()

    access_token = create_access_token(
        data={"sub": payload.username.strip(), "role": "super_admin", "uid": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=access_token, role="super_admin")


@router.post("/register", response_model=TokenResponse)
async def register(payload: AuthRegisterRequest):
    invite_code = payload.invite_code.strip()
    username = payload.username.strip()

    async with AsyncSessionLocal() as session:
        async with session.begin():
            existing_user = await session.execute(
                select(UserORM).where(UserORM.username == username)
            )
            if existing_user.scalar_one_or_none():
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="用户名已存在")

            invite_result = await session.execute(
                select(InvitationCodeORM).where(
                    InvitationCodeORM.code == invite_code,
                    InvitationCodeORM.is_used == False,
                )
            )
            invitation = invite_result.scalar_one_or_none()
            if not invitation:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="邀请码无效或已被使用")

            user = UserORM(
                username=username,
                hashed_password=get_password_hash(payload.password),
                role="user",
            )
            session.add(user)
            await session.flush()

            invitation.is_used = True
            invitation.used_by_user_id = user.id

    access_token = create_access_token(
        data={"sub": username, "role": "user", "uid": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=access_token, role="user")


@router.post("/login", response_model=TokenResponse)
async def login(payload: AuthLoginRequest):
    async with AsyncSessionLocal() as session:
        result = await session.execute(
            select(UserORM).where(UserORM.username == payload.username.strip())
        )
        user = result.scalar_one_or_none()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "uid": user.id},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=access_token, role=user.role)


@router.post("/change_password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user=Depends(get_current_user),
):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            user = await session.get(UserORM, current_user["id"])
            if not user:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")

            if not verify_password(payload.current_password, user.hashed_password):
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="当前密码错误")

            user.hashed_password = get_password_hash(payload.new_password)

    return {"status": "success", "message": "密码已更新"}
