"""Call real model services through Pekno's assignments.

uv run python scripts/smoke_model_providers.py --base-url http://host:8080/v1 --model model-name
Use --embedding-model only when the server exposes an embedding model.
An optional API key is read from --key-env (never printed).
Configuration and billing are isolated. --database-roundtrip additionally writes
temporary test rows to the configured database and removes them afterwards.
"""

import argparse
import asyncio
import json
import os
import sys
import time
import uuid
import math
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from hub.core import model_settings as settings
from hub.core.llm.providers import openai_adapter, openai_client
from shared.ai_validation import EMBEDDING_DIMENSIONS, validate_embedding


async def run(args):
    store = {}
    clients = []
    requests = []
    response_metadata = []
    results = []
    key = os.environ.get(args.key_env, "").strip() if args.key_env else ""
    original_client = openai_client.openai.AsyncOpenAI

    async def get_config(namespace, config_key, default=None, **kwargs):
        return store.get(config_key, default)

    async def set_config(namespace, config_key, value, **kwargs):
        store[config_key] = value
        return True

    async def inspect_request(request):
        requests.append(request)
        assert (request.headers.get("Authorization") == f"Bearer {key}") if key else ("Authorization" not in request.headers)

    async def inspect_response(response):
        await response.aread()
        metadata = {"http_status": response.status_code, "interface_success": response.is_success}
        if response.is_success:
            data = response.json()
            choice = (data.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            if response.request.url.path.endswith("/embeddings"):
                vector = (data.get("data") or [{}])[0].get("embedding")
                metadata["actual_dimension"] = len(vector) if isinstance(vector, list) else None
                metadata["expected_dimension"] = EMBEDDING_DIMENSIONS
            if choice:
                metadata.update(
                    finish_reason=choice.get("finish_reason"),
                    content_size=len(message.get("content") or ""),
                    reasoning_size=len(message.get("reasoning_content") or ""),
                )
        response_metadata.append(metadata)

    def create_client(**kwargs):
        kwargs.update(
            http_client=httpx.AsyncClient(event_hooks={"request": [inspect_request], "response": [inspect_response]}),
            max_retries=0,
            timeout=args.timeout,
        )
        client = original_client(**kwargs)
        clients.append(client)
        return client

    async def check(provider_id, purpose, model):
        await settings.save_model_assignments([{"key": purpose, "provider": provider_id, "model": model}])
        started = time.monotonic()
        response_count = len(response_metadata)
        print(json.dumps({"provider": provider_id, "purpose": purpose, "status": "running"}), flush=True)
        try:
            if purpose == "tagging":
                output, actual_model = await settings.extract_tags("Pekno stores articles and generates searchable summaries.", preferred_locale="en")
            elif purpose == "embedding":
                output, actual_model = await settings.embed_text("Pekno stores searchable knowledge.")
            else:
                output, actual_model = await settings.generate_summary(
                    "Pekno stores articles, extracts tags and creates summaries for a searchable personal knowledge base.",
                    length="long" if purpose == "long_summary" else "short",
                    preferred_locale="en",
                )
            assert actual_model == model
            assert output.strip() if isinstance(output, str) else output, "Model returned an empty result"
            if purpose == "short_summary":
                # The fixture requests an English summary of knowledge software.
                assert 5 <= len(output.split()) <= 100 and len(output) <= 600
                assert "<think>" not in output.lower() and "<analysis>" not in output.lower()
                assert any(word in output.lower() for word in ("knowledge", "summar", "article", "document", "information"))
            if purpose == "embedding":
                validate_embedding(output)
            result = {"provider": provider_id, "purpose": purpose, "model": model, "status": "passed", "output_size": len(output)}
        except Exception as exc:
            # Avoid printing exception messages, which can contain server bodies or secrets.
            result = {"provider": provider_id, "purpose": purpose, "model": model, "status": "failed", "exception": type(exc).__name__}
            if getattr(exc, "error_code", None):
                result["error_code"] = exc.error_code
            if purpose == "embedding":
                result["storage_compatible"] = False
                result["expected_dimension"] = EMBEDDING_DIMENSIONS
                if hasattr(exc, "actual_dimension"):
                    result["actual_dimension"] = exc.actual_dimension
            if getattr(exc, "status_code", None):
                result["http_status"] = exc.status_code
        if purpose == "embedding" and result["status"] == "passed":
            result["storage_compatible"] = True
        result["elapsed_seconds"] = round(time.monotonic() - started, 2)
        if len(response_metadata) > response_count:
            result.update(response_metadata[-1])
        results.append(result)
        print(json.dumps(result), flush=True)

    # Only configuration persistence and billing are isolated. SDK calls use real HTTP.
    with (
        patch.object(settings.ConfigManager, "get_config", get_config),
        patch.object(settings.ConfigManager, "set_config", set_config),
        patch.object(settings, "check_api_limit_or_raise", AsyncMock()),
        patch.object(settings, "record_api_usage", AsyncMock()),
        patch.object(openai_adapter, "check_api_limit_or_raise", AsyncMock()),
        patch.object(openai_adapter, "record_api_usage", AsyncMock()),
        patch.object(openai_client.openai, "AsyncOpenAI", create_client),
        patch.dict(os.environ, {"OPENAI_API_KEY": "pekno-smoke-environment-key-must-not-be-used"}),
    ):
        try:
            for provider_id in args.provider or ("openai_compatible", "llama_cpp"):
                # Exercise both forms of the address using the same live service.
                base_url = args.base_url.rstrip("/")
                if provider_id == "openai_compatible" and base_url.endswith("/v1"):
                    base_url = base_url[:-3]
                await settings.save_model_provider_config(provider_id, {"base_url": base_url + "/", "api_key": key, "thinking_mode": args.thinking_mode})
                refreshed = await settings.get_model_provider_state()
                state = next(p for p in refreshed["providers"] if p["id"] == provider_id)
                assert state["is_configured"] and state["config"]["api_key"] == ""
                for purpose in args.purpose or ("tagging", "short_summary", "long_summary", "embedding"):
                    if purpose == "embedding":
                        if args.embedding_model:
                            await check(provider_id, purpose, args.embedding_model)
                    else:
                        await check(provider_id, purpose, args.model)
                if args.database_roundtrip:
                    await database_roundtrip(provider_id, args.embedding_model, results)
        finally:
            for client in clients:
                await client.close()
    print(json.dumps({"requests": len(requests), "authentication": "explicit_key" if key else "no_authorization_header", "passed": sum(r["status"] == "passed" for r in results), "failed": sum(r["status"] == "failed" for r in results)}), flush=True)
    return 1 if any(r["status"] != "passed" for r in results) else 0


async def database_roundtrip(provider_id, model, results):
    from sqlalchemy import delete, select, func
    from shared.database import AsyncSessionLocal, engine
    from shared.entities import UniversalItem
    from shared.models import ItemORM, UserORM
    from hub.core.search import SearchService
    # Initialize the existing broker in its normal import order. Do not change
    # the application's log files or dispatch any jobs during this smoke run.
    with patch("shared.logger.configure_logging"):
        import worker.broker
        from worker.ingestion.pipeline import IngestionPipeline

    marker = "v031-smoke-" + uuid.uuid4().hex
    user_id = marker
    item_ids = [marker + "-knowledge", marker + "-garden"]
    await settings.save_model_assignments([{"key": "embedding", "provider": provider_id, "model": model}])
    result = {"provider": provider_id, "purpose": "embedding_database_roundtrip", "model": model, "expected_dimension": EMBEDDING_DIMENSIONS}
    try:
        async with AsyncSessionLocal() as session:
            session.add(UserORM(id=user_id, username=marker, hashed_password="smoke-account-login-disabled"))
            await session.commit()
        pipeline = IngestionPipeline()
        for item_id, title, content in (
            (item_ids[0], "Knowledge software", "Pekno organizes documents and summaries into a searchable personal knowledge base."),
            (item_ids[1], "Garden care", "Tomato plants need sunlight, water and fertile soil to produce ripe vegetables."),
        ):
            item = UniversalItem(id=item_id, title=title, content_text=content, summary=content, source_type="v031_smoke", raw_link="https://example.invalid/" + item_id, intent="article", source_user_id=user_id)
            await pipeline._store_to_vector_db(item, title + "\n" + content)
        async with AsyncSessionLocal() as session:
            dimensions = (await session.execute(select(func.vector_dims(ItemORM.embedding)).where(ItemORM.id.in_(item_ids)))).scalars().all()
        assert dimensions == [EMBEDDING_DIMENSIONS] * 2
        hits = await SearchService()._get_vector_candidates(
            "A tool to retrieve and organize my personal documents and knowledge.", user_id=user_id, limit=2,
        )
        assert len(hits) == 2 and hits[0][0].id == item_ids[0]
        assert all(math.isfinite(distance) for _, distance in hits)
        result.update(status="passed", stored_dimensions=dimensions, stored_rows=2, semantic_top_hit="knowledge", cosine_distance=round(hits[0][1], 6))
    except Exception as exc:
        result.update(status="failed", exception=type(exc).__name__)
        if getattr(exc, "error_code", None):
            result["error_code"] = exc.error_code
    finally:
        async with AsyncSessionLocal() as session:
            await session.execute(delete(UserORM).where(UserORM.id == user_id))
            await session.execute(delete(ItemORM).where(ItemORM.id.in_(item_ids)))
            await session.commit()
        await engine.dispose()
    results.append(result)
    print(json.dumps(result), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--embedding-model")
    parser.add_argument("--key-env", help="Name of an environment variable containing the service API key")
    parser.add_argument("--provider", action="append", choices=("openai_compatible", "llama_cpp"))
    parser.add_argument("--purpose", action="append", choices=("tagging", "short_summary", "long_summary", "embedding"))
    parser.add_argument("--thinking-mode", choices=("auto", "enabled", "disabled"), default="auto")
    parser.add_argument("--database-roundtrip", action="store_true", help="Write isolated test records to the configured migrated database, query, then clean them up")
    parser.add_argument("--timeout", type=float, default=120)
    args = parser.parse_args()
    if args.key_env and not os.environ.get(args.key_env, "").strip():
        parser.error("The selected key environment variable is empty")
    if args.database_roundtrip and not args.embedding_model:
        parser.error("--database-roundtrip requires --embedding-model")
    if args.purpose and "embedding" in args.purpose and not args.embedding_model:
        parser.error("--purpose embedding requires --embedding-model")
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
