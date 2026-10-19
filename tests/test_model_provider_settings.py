"""Provider state and actual SDK request regressions (no DB or paid API calls)."""

import json
from unittest.mock import AsyncMock

import httpx
import openai
import pytest
import pytest_asyncio

from hub.core import model_settings as settings
from hub.core.llm.providers import openai_adapter, openai_client
from shared.api_errors import ApiError
from shared.config import SYSTEM_CONFIG_USER_ID
from shared.error_codes import ERR_INTERNAL_SERVER_ERROR, ERR_INVALID_INPUT


@pytest.fixture
def config_store(monkeypatch):
    store = {}

    async def get_config(namespace, key, default=None, user_id=None):
        assert namespace == settings.MODEL_SETTINGS_NAMESPACE
        assert user_id == SYSTEM_CONFIG_USER_ID
        return store.get(key, default)

    async def set_config(namespace, key, value, description=None, user_id=None):
        assert namespace == settings.MODEL_SETTINGS_NAMESPACE
        assert user_id == SYSTEM_CONFIG_USER_ID
        store[key] = value
        return True

    monkeypatch.setattr(settings.ConfigManager, "get_config", get_config)
    monkeypatch.setattr(settings.ConfigManager, "set_config", set_config)
    return store


def provider_state(state, provider_id):
    return next(p for p in state["providers"] if p["id"] == provider_id)


@pytest.mark.asyncio
async def test_defaults_do_not_mark_remote_services_configured(config_store):
    state = await settings.get_model_provider_state()
    for provider in state["providers"]:
        assert provider["is_configured"] == (provider["id"] in {"local_whisper", "paddleocr_v5_cpu"})
        assert provider["has_api_key"] is False
    assert not config_store


@pytest.mark.asyncio
@pytest.mark.parametrize("key", ["abc", "sk-regression-secret-123456"])
async def test_status_uses_real_config_and_never_returns_key(config_store, key):
    saved = await settings.save_model_provider_config("openai", {"api_key": key})
    refreshed = await settings.get_model_provider_state()
    for state in (saved, refreshed):
        provider = provider_state(state, "openai")
        assert provider["is_configured"] is True
        assert provider["has_api_key"] is True
        assert provider["config"]["api_key"] == ""
        assert provider["secret_preview"] == "********"
        assert key not in json.dumps(state)
    assert json.loads(config_store["provider_config::openai"])["api_key"] == key


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_id", ["openai_compatible", "llama_cpp"])
async def test_optional_key_status_requires_saved_address(config_store, provider_id):
    state = await settings.save_model_provider_config(provider_id, {"base_url": "http://localhost:8080/"})
    assert provider_state(state, provider_id)["is_configured"] is True
    assert provider_state(state, provider_id)["config"]["base_url"] == "http://localhost:8080/v1"
    state = await settings.save_model_provider_config(provider_id, {"base_url": "  "})
    assert provider_state(state, provider_id)["is_configured"] is False


CLOUD_PROVIDERS = [
    p["id"] for p in settings.MODEL_PROVIDER_CATALOG
    if any(f.get("key") == "api_key" and f.get("required") for f in p["config_fields"])
]


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_id", CLOUD_PROVIDERS)
async def test_cloud_key_still_required(config_store, provider_id):
    empty = await settings.save_model_provider_config(provider_id, {"api_key": "   "})
    assert provider_state(empty, provider_id)["is_configured"] is False
    valid = await settings.save_model_provider_config(provider_id, {"api_key": "test-cloud-key"})
    assert provider_state(valid, provider_id)["is_configured"] is True
    cleared = await settings.save_model_provider_config(provider_id, {"clear_api_key": True})
    assert provider_state(cleared, provider_id)["is_configured"] is False


@pytest.mark.asyncio
@pytest.mark.parametrize("blank", [None, "", "  ", "\t\n"])
async def test_blank_preserves_key_then_replace_and_explicit_clear(config_store, blank):
    await settings.save_model_provider_config("openai_compatible", {"api_key": "original-key"})
    await settings.save_model_provider_config("openai_compatible", {"api_key": blank})
    read = lambda: json.loads(config_store["provider_config::openai_compatible"])
    assert read()["api_key"] == "original-key"
    await settings.save_model_provider_config("openai_compatible", {"api_key": " new-key "})
    assert read()["api_key"] == "new-key"
    state = await settings.save_model_provider_config("openai_compatible", {"api_key": blank, "clear_api_key": True})
    assert read()["api_key"] == ""
    provider = provider_state(state, "openai_compatible")
    assert provider["has_api_key"] is False
    assert provider["secret_preview"] is None
    assert provider["is_configured"] is True
    assert "clear_api_key" not in read()


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [
    {"clear_api_key": "true"}, {"clear_api_key": None},
    {"clear_api_key": True, "api_key": "replacement"},
    {"api_key": 123}, {"base_url": []}, {"base_url": "not-a-url"},
])
async def test_invalid_updates_do_not_change_saved_key(config_store, payload):
    await settings.save_model_provider_config("openai_compatible", {"api_key": "original-key"})
    before = dict(config_store)
    with pytest.raises(ApiError) as error:
        await settings.save_model_provider_config("openai_compatible", payload)
    assert error.value.error_code == ERR_INVALID_INPUT
    assert config_store == before


@pytest.mark.asyncio
async def test_save_failure_returns_standard_error(config_store, monkeypatch):
    monkeypatch.setattr(settings.ConfigManager, "set_config", AsyncMock(return_value=False))
    with pytest.raises(ApiError) as error:
        await settings.save_model_provider_config("openai", {"api_key": "test-key"})
    assert error.value.error_code == ERR_INTERNAL_SERVER_ERROR
    assert error.value.status_code == 500


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", ["bad-json", "[]", "null", '"text"'])
async def test_invalid_saved_config_does_not_turn_default_address_green(config_store, raw):
    config_store["provider_config::openai_compatible"] = raw
    state = await settings.get_model_provider_state()
    assert provider_state(state, "openai_compatible")["is_configured"] is False


@pytest.mark.parametrize("url", [
    "http://localhost:8080", "http://localhost:8080/", "http://localhost:8080/v1", "http://localhost:8080/v1///",
])
def test_compatible_url_normalization(url):
    assert settings._normalize_compatible_base_url(url) == "http://localhost:8080/v1"


def test_url_prefix_and_official_version_are_preserved():
    assert settings._normalize_compatible_base_url("https://example.com/proxy/v1/") == "https://example.com/proxy/v1"
    _, url = settings._resolve_openai_config("zhipu", {"api_key": "test-key"})
    assert url.endswith("/api/paas/v4")
    _, url = settings._resolve_openai_config("groq", {"api_key": "test-key"})
    assert url.endswith("/openai/v1")


@pytest.mark.asyncio
async def test_llamacpp_configuration_and_assignments_are_independent(config_store):
    config_store["provider_config::openai_compatible"] = json.dumps({"api_key": "legacy-key", "base_url": "http://legacy:8000/v1/"})
    await settings.save_model_provider_config("llama_cpp", {"base_url": "http://llama:8080", "api_key": "llama-key"})
    purposes = ("tagging", "short_summary", "long_summary", "embedding")
    for provider_id in ("openai_compatible", "llama_cpp"):
        result = await settings.save_model_assignments([
            {"key": purpose, "provider": provider_id, "model": f"{provider_id}-model"} for purpose in purposes
        ])
        for assignment in result:
            if assignment["key"] in purposes:
                assert assignment["provider"] == provider_id
    legacy = json.loads(config_store["provider_config::openai_compatible"])
    assert legacy == {"api_key": "legacy-key", "base_url": "http://legacy:8000/v1/"}


@pytest_asyncio.fixture
async def sdk_transport(monkeypatch):
    requests = []
    clients = []
    behavior = {"failure": None, "embedding": [0.1] * 768, "summary": "alpha,beta", "finish_reason": "stop"}
    original_client = openai.AsyncOpenAI
    monkeypatch.setenv("OPENAI_API_KEY", "environment-key-must-never-be-used")
    monkeypatch.setattr(settings, "check_api_limit_or_raise", AsyncMock())
    monkeypatch.setattr(settings, "record_api_usage", AsyncMock())
    monkeypatch.setattr(openai_adapter, "check_api_limit_or_raise", AsyncMock())
    monkeypatch.setattr(openai_adapter, "record_api_usage", AsyncMock())

    def respond(request):
        requests.append(request)
        if behavior["failure"] == "timeout":
            raise httpx.ReadTimeout("private-upstream-payload", request=request)
        if behavior["failure"] == "unreachable":
            raise httpx.ConnectError("Service unreachable", request=request)
        if behavior["failure"] == "wrong_key":
            return httpx.Response(401, json={"error": {"message": "Invalid key", "type": "authentication_error"}})
        payload = json.loads(request.content)
        if request.url.path.endswith("/embeddings"):
            body = {"object": "list", "model": payload["model"], "data": [{"index": 0, "object": "embedding", "embedding": behavior["embedding"]}], "usage": {"prompt_tokens": 3, "total_tokens": 3}}
            # Some services emit non-standard NaN/Infinity JSON. Exercise that
            # response at the SDK boundary rather than failing in httpx's encoder.
            return httpx.Response(200, content=json.dumps(body), headers={"Content-Type": "application/json"})
        return httpx.Response(200, json={"id": "chat-test", "object": "chat.completion", "created": 1, "model": payload["model"], "choices": [{"index": 0, "message": {"role": "assistant", "content": behavior["summary"]}, "finish_reason": behavior["finish_reason"]}], "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}})

    def factory(**kwargs):
        kwargs.update(http_client=httpx.AsyncClient(transport=httpx.MockTransport(respond)), max_retries=0)
        client = original_client(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(openai_client.openai, "AsyncOpenAI", factory)
    yield requests, behavior
    for client in clients:
        await client.close()


async def assign_and_call(provider_id, purpose):
    await settings.save_model_assignments([{"key": purpose, "provider": provider_id, "model": "test-model"}])
    if purpose == "embedding":
        return await settings.embed_text("Example content")
    if purpose == "tagging":
        return await settings.extract_tags("Example content")
    return await settings.generate_summary("Example content", length="long" if purpose == "long_summary" else "short")


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_id", ["openai_compatible", "llama_cpp"])
@pytest.mark.parametrize("purpose", ["tagging", "short_summary", "long_summary", "embedding"])
@pytest.mark.parametrize("key", [None, "", "test-explicit-key"])
async def test_sdk_auth_headers_and_call_paths(config_store, sdk_transport, provider_id, purpose, key):
    requests, _ = sdk_transport
    await settings.save_model_provider_config(provider_id, {"base_url": "http://model.test:8080/", "api_key": key})
    result, model = await assign_and_call(provider_id, purpose)
    assert model == "test-model"
    assert result == ([0.1] * 768 if purpose == "embedding" else ["alpha", "beta"] if purpose == "tagging" else "alpha,beta")
    assert len(requests) == 1
    assert requests[0].url.path == ("/v1/embeddings" if purpose == "embedding" else "/v1/chat/completions")
    if key:
        assert requests[0].headers["Authorization"] == f"Bearer {key}"
    else:
        assert "Authorization" not in requests[0].headers
    assert "environment-key-must-never-be-used" not in str(requests[0].headers)


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_id", ["openai_compatible", "llama_cpp"])
@pytest.mark.parametrize("purpose", ["tagging", "short_summary", "long_summary", "embedding"])
async def test_clear_key_switches_actual_requests_to_no_auth(config_store, sdk_transport, provider_id, purpose):
    requests, _ = sdk_transport
    await settings.save_model_provider_config(provider_id, {"base_url": "http://model.test:8080", "api_key": "old-key"})
    await assign_and_call(provider_id, purpose)
    await settings.save_model_provider_config(provider_id, {"api_key": " ", "clear_api_key": True})
    await assign_and_call(provider_id, purpose)
    assert requests[0].headers["Authorization"] == "Bearer old-key"
    assert "Authorization" not in requests[1].headers


@pytest.mark.asyncio
@pytest.mark.parametrize("provider_id", ["openai_compatible", "llama_cpp"])
@pytest.mark.parametrize("purpose", ["tagging", "short_summary", "long_summary", "embedding"])
@pytest.mark.parametrize("failure,exception", [("wrong_key", openai.AuthenticationError), ("unreachable", openai.APIConnectionError)])
async def test_model_failures_propagate(config_store, sdk_transport, provider_id, purpose, failure, exception):
    _, behavior = sdk_transport
    behavior["failure"] = failure
    await settings.save_model_provider_config(provider_id, {"base_url": "http://model.test:8080", "api_key": "wrong-key"})
    with pytest.raises(ApiError if purpose in {"short_summary", "long_summary"} else exception) as error:
        await assign_and_call(provider_id, purpose)
    if purpose in {"short_summary", "long_summary"}:
        assert error.value.error_code == "ERR_AI_UNAVAILABLE"


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose", ["tagging", "short_summary", "long_summary", "embedding"])
async def test_cloud_missing_key_never_uses_environment_key(config_store, sdk_transport, purpose):
    requests, _ = sdk_transport
    with pytest.raises(ApiError) as error:
        await assign_and_call("openai", purpose)
    assert error.value.error_code == ERR_INVALID_INPUT
    assert not requests


@pytest.mark.asyncio
async def test_admin_api_save_refresh_clear_and_standard_errors(config_store):
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from hub.api.routers import admin

    app = FastAPI()
    app.include_router(admin.router)
    app.dependency_overrides[admin.require_admin] = lambda: {"id": "admin-test", "role": "admin"}

    @app.exception_handler(ApiError)
    async def handle_error(request, exc):
        return JSONResponse(status_code=exc.status_code, content={"error_code": exc.error_code, "detail": exc.detail})

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        route = "/api/admin/models/providers"
        saved = await client.put(route + "/openai", json={"api_key": "api-test-secret"})
        refreshed = await client.get(route)
        for response in (saved, refreshed):
            assert response.status_code == 200
            state = provider_state(response.json(), "openai")
            assert state["is_configured"] is True
            assert state["has_api_key"] is True
            assert "api-test-secret" not in response.text
        cleared = await client.put(route + "/openai", json={"clear_api_key": True})
        assert cleared.status_code == 200
        assert provider_state(cleared.json(), "openai")["is_configured"] is False
        invalid = await client.put(route + "/openai", json={"clear_api_key": "true"})
        assert invalid.status_code == 400
        assert invalid.json()["error_code"] == ERR_INVALID_INPUT


def test_existing_compatible_custom_api_prefix_is_preserved():
    _, url = settings._resolve_openai_config("openai_compatible", {"base_url": "https://example.com/gateway/api/", "api_key": "legacy-key"})
    assert url == "https://example.com/gateway/api"


@pytest.mark.asyncio
@pytest.mark.parametrize("purpose", ["tagging", "short_summary", "long_summary", "embedding"])
async def test_official_provider_sends_explicit_key(config_store, sdk_transport, purpose):
    requests, _ = sdk_transport
    await settings.save_model_provider_config("openai", {"api_key": "official-test-key"})
    await assign_and_call("openai", purpose)
    assert requests[0].headers["Authorization"] == "Bearer official-test-key"
    assert requests[0].url.host == "api.openai.com"
