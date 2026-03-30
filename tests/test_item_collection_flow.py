from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.api.routers import items as items_router
from hub.core.security import get_current_user


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _BeginCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(items_router.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-1",
        "username": "tester",
        "role": "user",
    }
    return app


def test_upload_deduplicates_by_file_hash(monkeypatch, tmp_path: Path):
    existing_holder: dict[str, object | None] = {"item": None}
    store_calls: list[dict] = []
    ensure_calls: list[dict] = []

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            return _ScalarResult(existing_holder["item"])

    monkeypatch.setattr(items_router, "UPLOAD_ROOT", tmp_path)
    monkeypatch.setattr(items_router, "AsyncSessionLocal", lambda: FakeSession())

    async def fake_store_user_item(item_data, user_id: str, *, retention_days: int = -1):
        store_calls.append({"item_data": item_data, "user_id": user_id, "retention_days": retention_days})
        existing_holder["item"] = SimpleNamespace(
            id="upload_existing",
            title=item_data["title"],
            source_type=item_data["source_type"],
            raw_link=item_data["raw_link"],
            content_text=item_data["content_text"],
            summary=item_data["summary"],
            tags=item_data["tags"],
            intent=item_data["intent"],
            created_at="2026-03-30T00:00:00",
            metadata_extra=item_data["metadata_extra"],
            local_asset_path=item_data["local_asset_path"],
            file_hash=item_data["file_hash"],
        )
        return "upload_existing"

    async def fake_fetch_item_for_user(item_id: str, user_id: str):
        return existing_holder["item"], SimpleNamespace(is_read=False, is_watch_later=False, is_favorited=False)

    async def fake_ensure_user_item_state(user_id: str, item_id: str, *, is_watch_later=None, is_favorited=None):
        ensure_calls.append(
            {"user_id": user_id, "item_id": item_id, "is_watch_later": is_watch_later, "is_favorited": is_favorited}
        )
        return SimpleNamespace(
            is_read=False,
            is_watch_later=bool(is_watch_later),
            is_favorited=bool(is_favorited),
        )

    monkeypatch.setattr(items_router, "_store_user_item", fake_store_user_item)
    monkeypatch.setattr(items_router, "_fetch_item_for_user", fake_fetch_item_for_user)
    monkeypatch.setattr(items_router, "_ensure_user_item_state", fake_ensure_user_item_state)

    with TestClient(_build_test_app()) as client:
        first_response = client.post(
            "/api/items/upload",
            files={"file": ("hello.txt", b"same-bytes", "text/plain")},
            data={"title": "hello"},
        )
        second_response = client.post(
            "/api/items/upload",
            files={"file": ("hello-copy.txt", b"same-bytes", "text/plain")},
            data={"title": "hello again", "auto_favorite": "true"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 409
    assert second_response.json()["deduplicated"] is True
    assert second_response.json()["item_id"] == "upload_existing"
    assert len(store_calls) == 1
    assert len(list(tmp_path.rglob("*.*"))) == 1
    assert ensure_calls[-1]["is_favorited"] is True


def test_favorite_only_queues_vault_download_on_first_toggle(monkeypatch):
    queued_item_ids: list[str] = []
    state = SimpleNamespace(is_read=False, is_watch_later=False, is_favorited=False, updated_at=None)
    item = SimpleNamespace(
        id="video-1",
        source_type="bilibili_subscribed",
        raw_link="https://www.bilibili.com/video/BV1demo",
        local_asset_path=None,
    )

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return _BeginCtx()

        async def get(self, model, item_id):
            return item if item_id == item.id else None

        async def execute(self, stmt):
            return _ScalarResult(state)

    async def fake_queue_vault_download_if_needed(item_id: str, item_obj):
        queued_item_ids.append(item_id)

    monkeypatch.setattr(items_router, "AsyncSessionLocal", lambda: FakeSession())
    monkeypatch.setattr(items_router, "_queue_vault_download_if_needed", fake_queue_vault_download_if_needed)

    with TestClient(_build_test_app()) as client:
        first_response = client.post(f"/api/items/{item.id}/favorite")
        second_response = client.post(f"/api/items/{item.id}/favorite")

    assert first_response.status_code == 200
    assert first_response.json()["is_favorited"] is True
    assert second_response.status_code == 200
    assert second_response.json()["is_favorited"] is False
    assert queued_item_ids == [item.id]
