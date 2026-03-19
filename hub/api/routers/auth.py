from datetime import timedelta

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import func, select

from hub.api.schemas import (
    AuthInitRequest,
    AuthLoginRequest,
    AuthStatusResponse,
    TokenResponse,
)
from hub.core.security import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    create_access_token,
    get_password_hash,
    verify_password,
)
from shared.database import AsyncSessionLocal
from shared.models import UserORM

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

    access_token = create_access_token(
        data={"sub": payload.username.strip(), "role": "super_admin"},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=access_token, role="super_admin")


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
        data={"sub": user.username, "role": user.role},
        expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return TokenResponse(access_token=access_token, role=user.role)
