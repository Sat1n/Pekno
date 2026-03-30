from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from hub.api.routers import annotations as annotations_router
from hub.api.routers import items as items_router
from hub.core.security import get_current_user


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _ScalarsWrapper:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _RowsResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _ScalarsWrapper(self._values)


class _BeginCtx:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(annotations_router.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "id": "user-1",
        "username": "tester",
        "role": "user",
    }
    return app


def test_get_annotations_returns_only_current_user_records_in_desc_order(monkeypatch):
    newer = SimpleNamespace(
        id="note-2",
        user_id="user-1",
        item_id="item-1",
        type="general",
        content_raw="second",
        anchor_data={},
        created_at=datetime(2026, 3, 30, 12, 0, 0),
    )
    older = SimpleNamespace(
        id="note-1",
        user_id="user-1",
        item_id="item-1",
        type="general",
        content_raw="first",
        anchor_data={},
        created_at=datetime(2026, 3, 30, 11, 0, 0),
    )

    call_state = {"count": 0}

    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            call_state["count"] += 1
            if call_state["count"] == 1:
                return _ScalarResult("item-1")
            return _RowsResult([newer, older])

    monkeypatch.setattr(annotations_router, "AsyncSessionLocal", lambda: FakeSession())

    with TestClient(_build_test_app()) as client:
        response = client.get("/api/items/item-1/annotations")

    assert response.status_code == 200
    data = response.json()
    assert [row["id"] for row in data] == ["note-2", "note-1"]
    assert all(row["item_id"] == "item-1" for row in data)


def test_create_annotation_succeeds_for_visible_item(monkeypatch):
    added = []

    class FakeSession:
        def __init__(self):
            self.call_index = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def begin(self):
            return _BeginCtx()

        async def execute(self, stmt):
            self.call_index += 1
            return _ScalarResult("item-1")

        def add(self, obj):
            added.append(obj)

    monkeypatch.setattr(annotations_router, "AsyncSessionLocal", lambda: FakeSession())

    with TestClient(_build_test_app()) as client:
        response = client.post(
            "/api/items/item-1/annotations",
            json={"content_raw": "new thought", "type": "general", "anchor_data": {}},
        )

    assert response.status_code == 200
    assert response.json()["content_raw"] == "new thought"
    assert len(added) == 1
    assert added[0].item_id == "item-1"
    assert added[0].user_id == "user-1"


def test_create_annotation_rejects_invisible_item(monkeypatch):
    class FakeSession:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, stmt):
            return _ScalarResult(None)

    monkeypatch.setattr(annotations_router, "AsyncSessionLocal", lambda: FakeSession())

    with TestClient(_build_test_app()) as client:
        response = client.post("/api/items/item-404/annotations", json={"content_raw": "blocked"})

    assert response.status_code == 404


def test_local_asset_url_maps_uploads_directory(monkeypatch, tmp_path):
    uploads_root = tmp_path / "uploads"
    asset_path = uploads_root / "vault" / "demo" / "source.mp4"
    asset_path.parent.mkdir(parents=True, exist_ok=True)
    asset_path.write_bytes(b"demo")

    monkeypatch.setattr(items_router, "UPLOAD_ROOT", uploads_root)

    mapped = items_router._build_local_asset_url(str(asset_path))
    outside = items_router._build_local_asset_url(str(tmp_path / "outside.mp4"))

    assert mapped == "/uploads/vault/demo/source.mp4"
    assert outside is None
