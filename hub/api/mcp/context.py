from __future__ import annotations

from typing import Any


def get_request_scope(server) -> dict[str, Any]:
    request = getattr(server.request_context, "request", None)
    return getattr(request, "scope", {}) if request else {}


def get_request_state(server) -> dict[str, Any]:
    scope = get_request_scope(server)
    return scope.get("state", {}) or {}


def get_user_id(server) -> str | None:
    return get_request_state(server).get("user_id")


def get_username(server) -> str | None:
    return get_request_state(server).get("username")


def get_role(server) -> str | None:
    return get_request_state(server).get("role")


def get_is_admin(server) -> bool:
    return bool(get_request_state(server).get("is_admin"))


def get_scopes(server) -> list[str]:
    scopes = get_request_state(server).get("scopes") or []
    return list(scopes) if isinstance(scopes, list) else []
