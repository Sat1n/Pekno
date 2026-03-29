import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select

from shared.database import AsyncSessionLocal
from shared.models import PersonalAccessTokenORM, UserORM
from shared.secret_store import load_or_create_secret
from shared.time_utils import now_in_app_timezone_naive

pwd_context = CryptContext(
    schemes=["pbkdf2_sha256", "bcrypt_sha256", "bcrypt"],
    deprecated="auto",
)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")

SECRET_KEY = load_or_create_secret(
    env_key="JWT_SECRET_KEY",
    filename="jwt_secret_key",
    generator=lambda: os.urandom(32).hex(),
    announce_label="JWT 签名密钥",
)
ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "120"))


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: Dict[str, Any], expires_delta: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def generate_personal_access_token() -> str:
    return f"pekno_pat_{secrets.token_urlsafe(24)}"


async def get_current_user(token: str = Depends(oauth2_scheme)) -> Dict[str, Any]:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证登录凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if token.startswith("pekno_pat_"):
        async with AsyncSessionLocal() as session:
            async with session.begin():
                result = await session.execute(
                    select(PersonalAccessTokenORM).where(PersonalAccessTokenORM.token == token)
                )
                pat = result.scalar_one_or_none()
                if not pat:
                    raise credentials_exception
                if pat.expires_at and pat.expires_at < now_in_app_timezone_naive():
                    raise credentials_exception
                user = await session.get(UserORM, pat.user_id)
                if not user:
                    raise credentials_exception
                pat.last_used_at = now_in_app_timezone_naive()
        return {
            "id": user.id,
            "username": user.username,
            "role": "admin" if pat.is_admin else user.role,
            "is_admin": bool(pat.is_admin),
            "scopes": list(pat.scopes or []),
        }

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        role = payload.get("role")
        if not username:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    async with AsyncSessionLocal() as session:
        result = await session.execute(select(UserORM).where(UserORM.username == username))
        user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    resolved_role = role or user.role
    return {
        "id": user.id,
        "username": user.username,
        "role": resolved_role,
        "is_admin": resolved_role in {"admin", "super_admin"},
        "scopes": [],
    }


def require_admin(current_user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    if current_user["role"] not in {"admin", "super_admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="仅管理员可以执行该操作",
        )
    return current_user
