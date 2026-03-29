from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from shared.database import AsyncSessionLocal
from shared.models import PersonalAccessTokenORM, UserORM
from shared.time_utils import now_in_app_timezone_naive


class MCPAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return

        auth_header = self._extract_authorization(scope)
        if not auth_header or not auth_header.startswith("Bearer "):
            await self._send_unauthorized(scope, send, "Missing authorization")
            return

        token = auth_header[7:].strip()
        identity = await self._validate_pat(token)
        if not identity:
            await self._send_unauthorized(scope, send, "Invalid token")
            return

        state = scope.setdefault("state", {})
        state["user_id"] = identity["user_id"]
        state["username"] = identity["username"]
        state["role"] = identity["role"]
        state["is_admin"] = identity["is_admin"]
        state["scopes"] = identity["scopes"]

        await self.app(scope, receive, send)

    @staticmethod
    def _extract_authorization(scope: dict[str, Any]) -> str | None:
        for key, value in scope.get("headers", []):
            if key.decode("latin-1").lower() == "authorization":
                return value.decode("latin-1")
        return None

    async def _send_unauthorized(self, scope, send, detail: str) -> None:
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 4401, "reason": detail})
            return

        body = json.dumps({"detail": detail}).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json; charset=utf-8"),
                    (b"www-authenticate", b"Bearer"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})

    @staticmethod
    async def _validate_pat(token: str) -> dict[str, Any] | None:
        if not token.startswith("pekno_pat_"):
            return None

        async with AsyncSessionLocal() as session:
            async with session.begin():
                result = await session.execute(
                    select(PersonalAccessTokenORM).where(PersonalAccessTokenORM.token == token)
                )
                pat = result.scalar_one_or_none()
                if not pat:
                    return None
                if pat.expires_at and pat.expires_at < now_in_app_timezone_naive():
                    return None

                user = await session.get(UserORM, pat.user_id)
                if not user:
                    return None

                pat.last_used_at = now_in_app_timezone_naive()

        role = "admin" if pat.is_admin else user.role
        return {
            "user_id": user.id,
            "username": user.username,
            "role": role,
            "is_admin": bool(pat.is_admin),
            "scopes": list(pat.scopes or []),
        }
