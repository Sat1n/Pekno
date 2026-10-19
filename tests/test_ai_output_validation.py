"""Output contracts and failure behavior at model, database, and worker boundaries."""

import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.dialects import postgresql

from hub.core import model_settings as settings
from hub.core.llm import summary_call
from hub.core.llm.providers import ollama_adapter, openai_adapter, openai_client
from hub.core.search import SearchService
from shared.ai_validation import EMBEDDING_DIMENSIONS, validate_embedding
from shared.api_errors import ApiError
from shared.entities import UniversalItem
from shared.error_codes import (
    ERR_AI_EMPTY_SUMMARY, ERR_AI_TIMEOUT, ERR_AI_UNAVAILABLE,
    ERR_EMBEDDING_DIMENSION_MISMATCH, ERR_EMBEDDING_INVALID,
)
from shared.models import ItemORM
from test_model_provider_settings import config_store, sdk_transport, assign_and_call


INVALID_VECTORS = [
    ([0.1] * 1024, ERR_EMBEDDING_DIMENSION_MISMATCH, 1024),
    ([], ERR_EMBEDDING_INVALID, 0),
    ([float('nan')] + [0.1] * 767, ERR_EMBEDDING_INVALID, 768),
    ([float('inf')] + [0.1] * 767, ERR_EMBEDDING_INVALID, 768),
    ([float('-inf')] + [0.1] * 767, ERR_EMBEDDING_INVALID, 768),
    ([1e100] + [0.1] * 767, ERR_EMBEDDING_INVALID, 768),
    ([True] + [0.1] * 767, ERR_EMBEDDING_INVALID, 768),
    (['invalid'] + [0.1] * 767, ERR_EMBEDDING_INVALID, 768),
    (None, ERR_EMBEDDING_INVALID, None),
]


def assert_vector_error(error, code, dimension):
    assert error.error_code == code
    assert error.expected_dimension == 768
    assert error.actual_dimension == dimension
    assert 'expected dimension 768' in error.detail
    assert f'actual dimension {dimension}' in error.detail


def test_schema_and_validator_use_the_existing_768_dimension():
    assert ItemORM.__table__.c.embedding.type.dim == EMBEDDING_DIMENSIONS == 768
    assert validate_embedding([0.1] * 768) == [0.1] * 768


@pytest.mark.parametrize('vector,code,dimension', INVALID_VECTORS)
def test_invalid_embedding_contract(vector, code, dimension):
    with pytest.raises(ApiError) as error:
        validate_embedding(vector)
    assert_vector_error(error.value, code, dimension)


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_id', ['openai_compatible', 'llama_cpp'])
@pytest.mark.parametrize('vector,code,dimension', INVALID_VECTORS[:-1])
async def test_compatible_embedding_records_usage_before_rejection(config_store, sdk_transport, provider_id, vector, code, dimension):
    _, behavior = sdk_transport
    behavior['embedding'] = vector
    behavior['embedding_usage'] = {'prompt_tokens': 500, 'total_tokens': 500}
    await settings.save_model_provider_config(provider_id, {'base_url': 'http://model.test/v1'})
    with pytest.raises(ApiError) as error:
        await assign_and_call(provider_id, 'embedding')
    assert_vector_error(error.value, code, dimension)
    settings.record_api_usage.assert_awaited_once_with('test-model', 500, 0, 500)


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_id', ['openai_compatible', 'llama_cpp'])
async def test_invalid_embedding_without_reported_usage_records_estimate(config_store, sdk_transport, provider_id):
    _, behavior = sdk_transport
    behavior.update(embedding=[0.1] * 1024, embedding_usage=None)
    await settings.save_model_provider_config(provider_id, {'base_url': 'http://model.test/v1'})
    with pytest.raises(ApiError) as error:
        await assign_and_call(provider_id, 'embedding')
    assert_vector_error(error.value, ERR_EMBEDDING_DIMENSION_MISMATCH, 1024)
    settings.record_api_usage.assert_awaited_once_with('test-model', prompt_tokens=3, completion_tokens=0)


@pytest.mark.asyncio
@pytest.mark.parametrize('vector,code,dimension', INVALID_VECTORS)
async def test_ollama_embedding_uses_same_contract(config_store, monkeypatch, vector, code, dimension):
    monkeypatch.setattr(settings, 'check_api_limit_or_raise', AsyncMock())
    usage = AsyncMock()
    monkeypatch.setattr(settings, 'record_api_usage', usage)
    monkeypatch.setattr(settings, 'ensure_ollama_model', AsyncMock())
    monkeypatch.setattr(settings, 'OllamaEmbeddings', lambda **kw: SimpleNamespace(embed_query=lambda text: vector))
    await settings.save_model_assignments([{'key': 'embedding', 'provider': 'ollama', 'model': 'test-model'}])
    with pytest.raises(ApiError) as error:
        await settings.embed_text('Private source')
    assert_vector_error(error.value, code, dimension)
    usage.assert_awaited_once_with('test-model', prompt_tokens=3, completion_tokens=0, force_zero_cost=True)


@pytest.mark.asyncio
async def test_ollama_768_embedding_succeeds(config_store, monkeypatch):
    monkeypatch.setattr(settings, 'check_api_limit_or_raise', AsyncMock())
    monkeypatch.setattr(settings, 'record_api_usage', AsyncMock())
    monkeypatch.setattr(settings, 'ensure_ollama_model', AsyncMock())
    monkeypatch.setattr(settings, 'OllamaEmbeddings', lambda **kw: SimpleNamespace(embed_query=lambda text: [0.1] * 768))
    await settings.save_model_assignments([{'key': 'embedding', 'provider': 'ollama', 'model': 'test-model'}])
    vector, model = await settings.embed_text('Example')
    assert len(vector) == 768 and model == 'test-model'


@pytest.fixture
def worker_modules(monkeypatch):
    # Worker imports normally configure production log files. Tests isolate that
    # side effect and import the broker first, matching the worker entrypoint.
    monkeypatch.setattr('shared.logger.configure_logging', lambda *a, **kw: None)
    import worker.broker
    from worker.ingestion import pipeline
    from worker import tasks
    return pipeline, tasks


def make_item():
    return UniversalItem(id='contract-item', title='Public title', source_type='article', raw_link='https://example.invalid/item', intent='article', content_text='private-source-body', summary='Existing valid summary', auto_short_summary=True, capabilities=['summarize'], ai_processing_status='processing')


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_id', ['openai_compatible', 'llama_cpp'])
async def test_bad_dimension_prevents_ingestion_and_search_db_access(config_store, sdk_transport, worker_modules, monkeypatch, provider_id):
    from hub.core import search
    pipeline_module, _ = worker_modules
    _, behavior = sdk_transport
    behavior['embedding'] = [0.1] * 1024
    behavior['embedding_usage'] = {'prompt_tokens': 500, 'total_tokens': 500}
    await settings.save_model_provider_config(provider_id, {'base_url': 'http://model.test/v1'})
    await settings.save_model_assignments([{'key': 'embedding', 'provider': provider_id, 'model': 'test-model'}])
    db = Mock(side_effect=AssertionError('Vector SQL must not run'))
    monkeypatch.setattr(pipeline_module, 'AsyncSessionLocal', db)
    monkeypatch.setattr(search, 'AsyncSessionLocal', db)
    pipeline = pipeline_module.IngestionPipeline()
    with pytest.raises(ApiError) as error:
        await pipeline._store_to_vector_db(make_item(), 'Private text')
    assert error.value.error_code == ERR_EMBEDDING_DIMENSION_MISMATCH
    for method in (SearchService()._get_vector_candidates, SearchService().hybrid_search):
        with pytest.raises(ApiError) as error:
            await method('Private query', user_id='test-user')
        assert error.value.error_code == ERR_EMBEDDING_DIMENSION_MISMATCH
    db.assert_not_called()
    assert settings.record_api_usage.await_count == 3
    assert all(call.args == ('test-model', 500, 0, 500) for call in settings.record_api_usage.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize('provider_id', ['openai_compatible', 'llama_cpp'])
@pytest.mark.parametrize('content,finish_reason', [(None, 'stop'), ('', 'stop'), (' \t\n ', 'stop'), ('', 'length')])
async def test_empty_summary_is_standard_failure_with_safe_diagnostics(config_store, sdk_transport, caplog, provider_id, content, finish_reason):
    _, behavior = sdk_transport
    behavior.update(summary=content, finish_reason=finish_reason)
    await settings.save_model_provider_config(provider_id, {'base_url': 'http://model.test/v1', 'api_key': 'private-test-key'})
    with caplog.at_level(logging.INFO, logger='Pekno-Hub'):
        with pytest.raises(ApiError) as error:
            await assign_and_call(provider_id, 'short_summary')
    assert error.value.error_code == ERR_AI_EMPTY_SUMMARY
    assert 'task=short_summary' in caplog.text
    assert 'model=test-model' in caplog.text
    assert f'finish_reason={finish_reason}' in caplog.text
    assert 'elapsed_seconds=' in caplog.text
    assert 'outcome=failed' in caplog.text
    assert 'private-test-key' not in caplog.text
    assert 'Example content' not in caplog.text
    # The response was charged even though its final body was unusable.
    openai_adapter.record_api_usage.assert_awaited_once()


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,code', [('timeout', ERR_AI_TIMEOUT), ('unreachable', ERR_AI_UNAVAILABLE)])
async def test_transport_failure_is_bounded_and_propagated(config_store, sdk_transport, caplog, failure, code):
    _, behavior = sdk_transport
    behavior['failure'] = failure
    await settings.save_model_provider_config('openai_compatible', {'base_url': 'http://model.test/v1'})
    with caplog.at_level(logging.INFO, logger='Pekno-Hub'):
        with pytest.raises(ApiError) as error:
            await assign_and_call('openai_compatible', 'short_summary')
    assert error.value.error_code == code
    assert code in caplog.text
    assert 'private-upstream-payload' not in caplog.text


@pytest.mark.asyncio
async def test_total_summary_deadline(monkeypatch):
    monkeypatch.setattr(summary_call, 'SUMMARY_TOTAL_TIMEOUT_SECONDS', 0.01)
    async def hang():
        await asyncio.Event().wait()
    with pytest.raises(ApiError) as error:
        await summary_call.request_summary(hang, model='test', purpose='short_summary', record_usage=AsyncMock())
    assert error.value.error_code == ERR_AI_TIMEOUT


def test_client_retry_and_timeout_have_explicit_limits():
    assert openai_client.MODEL_MAX_RETRIES == 1
    assert openai_client.MODEL_REQUEST_TIMEOUT_SECONDS == 120
    assert openai_client.SUMMARY_TOTAL_TIMEOUT_SECONDS == 180


@pytest.mark.asyncio
@pytest.mark.parametrize('content', [None, '', ' \n '])
async def test_ollama_summary_rejects_empty_body(monkeypatch, content):
    provider = ollama_adapter.OllamaProvider.__new__(ollama_adapter.OllamaProvider)
    provider.model_name = 'ollama-test'
    provider._create_chat_completion = AsyncMock(return_value=SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content), finish_reason='length')]))
    monkeypatch.setattr(ollama_adapter, 'check_api_limit_or_raise', AsyncMock())
    monkeypatch.setattr(ollama_adapter, 'read_response_usage', lambda response: None)
    monkeypatch.setattr(ollama_adapter, 'record_api_usage', AsyncMock())
    with pytest.raises(ApiError) as error:
        await provider.generate_summary('private-source')
    assert error.value.error_code == ERR_AI_EMPTY_SUMMARY


@pytest.mark.asyncio
@pytest.mark.parametrize('failure', ['empty', 'timeout', 'unreachable'])
async def test_failed_summary_preserves_item_and_skips_persistence(config_store, sdk_transport, worker_modules, monkeypatch, failure):
    pipeline_module, _ = worker_modules
    _, behavior = sdk_transport
    if failure == 'empty':
        behavior['summary'] = ''
    else:
        behavior['failure'] = failure
    await settings.save_model_provider_config('llama_cpp', {'base_url': 'http://model.test/v1'})
    await settings.save_model_assignments([{'key': 'short_summary', 'provider': 'llama_cpp', 'model': 'test-model'}])
    pipeline = pipeline_module.IngestionPipeline()
    store = AsyncMock()
    tags = AsyncMock()
    monkeypatch.setattr(pipeline, '_store_to_vector_db', store)
    monkeypatch.setattr(pipeline, '_auto_tagging', tags)
    item = make_item()
    with pytest.raises(ApiError):
        await pipeline.process_item(item)
    assert item.summary == 'Existing valid summary'
    assert item.ai_processing_status.value == 'processing'
    store.assert_not_awaited()
    tags.assert_not_awaited()


class FakeSession:
    def __init__(self, item, statements):
        self.item, self.statements = item, statements
    async def __aenter__(self): return self
    async def __aexit__(self, *args): return False
    def begin(self): return self
    async def get(self, *args): return self.item
    async def execute(self, statement):
        self.statements.append(statement)
        return SimpleNamespace(scalar_one_or_none=lambda: self.item)
    async def commit(self): pass


def statement_values(statement):
    return statement.compile(dialect=postgresql.dialect()).params


@pytest.mark.asyncio
async def test_ingestion_task_restores_pending_without_summary_overwrite(worker_modules, monkeypatch):
    pipeline_module, _ = worker_modules
    item = SimpleNamespace(id='contract-item', summary='Existing valid summary', metadata_extra={})
    statements = []
    monkeypatch.setattr(pipeline_module, 'AsyncSessionLocal', lambda: FakeSession(item, statements))
    monkeypatch.setattr(pipeline_module.IngestionPipeline, 'process_item', AsyncMock(side_effect=ApiError(ERR_AI_EMPTY_SUMMARY, 'Empty summary', status_code=502)))
    await pipeline_module.process_new_item_task(make_item().model_dump())
    assert len(statements) == 1
    values = statement_values(statements[0])
    assert values['ai_processing_status'] == 'pending_ai'
    assert values['metadata_extra']['processing_status'] == 'failed'
    assert 'summary' not in values
    assert item.summary == 'Existing valid summary'


@pytest.mark.asyncio
async def test_uploaded_document_failure_does_not_complete_or_clear_summary(worker_modules, monkeypatch, tmp_path):
    _, tasks = worker_modules
    path = tmp_path / 'document.txt'
    path.write_text('Private document source')
    item = SimpleNamespace(id='contract-item', title='Public title', summary='Existing valid summary', embedding=None, tags=[], local_asset_path=str(path), metadata_extra={'mime_type': 'text/plain'})
    statements = []
    monkeypatch.setattr(tasks, 'AsyncSessionLocal', lambda: FakeSession(item, statements))
    monkeypatch.setattr(tasks.LLMManager, 'generate_summary', AsyncMock(side_effect=ApiError(ERR_AI_EMPTY_SUMMARY, 'Empty summary', status_code=502)))
    vector = AsyncMock()
    monkeypatch.setattr(tasks.LLMManager, 'get_vector', vector)
    notify = AsyncMock()
    monkeypatch.setattr(tasks, 'create_notification_for_item_users', notify)
    await tasks.process_uploaded_text_document_task(item.id, user_id='test-user')
    assert item.summary == 'Existing valid summary'
    assert all('summary' not in statement_values(s) for s in statements)
    assert all(statement_values(s).get('ai_processing_status') != 'completed' for s in statements)
    assert statement_values(statements[-1])['metadata_extra']['processing_status'] == 'failed'
    vector.assert_not_awaited()
    assert all(call.kwargs['type'] == 'error' for call in notify.await_args_list)


@pytest.mark.asyncio
@pytest.mark.parametrize('mode,expected', [('auto', None), ('enabled', True), ('disabled', False)])
async def test_thinking_controls_are_explicit_and_optional(config_store, sdk_transport, mode, expected):
    import json
    requests, _ = sdk_transport
    await settings.save_model_provider_config('llama_cpp', {'base_url': 'http://model.test/v1', 'thinking_mode': mode})
    await assign_and_call('llama_cpp', 'short_summary')
    payload = json.loads(requests[0].content)
    if expected is None:
        assert 'chat_template_kwargs' not in payload
    else:
        assert payload['chat_template_kwargs']['enable_thinking'] is expected


@pytest.mark.asyncio
async def test_invalid_thinking_mode_is_not_persisted(config_store):
    with pytest.raises(ApiError) as error:
        await settings.save_model_provider_config('llama_cpp', {'thinking_mode': 'invalid'})
    assert error.value.error_code == 'ERR_INVALID_INPUT'
    assert not config_store


@pytest.mark.asyncio
async def test_valid_summary_is_trimmed_without_logging_content(config_store, sdk_transport, caplog):
    _, behavior = sdk_transport
    behavior['summary'] = ' \nA private concise summary.\t '
    await settings.save_model_provider_config('llama_cpp', {'base_url': 'http://model.test/v1'})
    with caplog.at_level(logging.INFO, logger='Pekno-Hub'):
        summary, _ = await assign_and_call('llama_cpp', 'short_summary')
    assert summary == 'A private concise summary.'
    assert 'outcome=completed' in caplog.text
    assert 'A private concise summary.' not in caplog.text


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,code', [('timeout', ERR_AI_TIMEOUT), ('unreachable', ERR_AI_UNAVAILABLE)])
async def test_real_sdk_retry_count_is_bounded(monkeypatch, failure, code):
    import httpx
    import openai
    requests = []
    clients = []
    original = openai.AsyncOpenAI

    def respond(request):
        requests.append(request)
        if failure == 'timeout':
            raise httpx.ReadTimeout('private-upstream-body', request=request)
        raise httpx.ConnectError('private-upstream-body', request=request)

    def factory(**kwargs):
        kwargs['http_client'] = httpx.AsyncClient(transport=httpx.MockTransport(respond))
        client = original(**kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(openai_client.openai, 'AsyncOpenAI', factory)
    monkeypatch.setattr(openai_adapter, 'check_api_limit_or_raise', AsyncMock())
    provider = openai_adapter.OpenAIProvider('', 'http://model.test/v1', 'test')
    try:
        with pytest.raises(ApiError) as error:
            await provider.generate_summary('Private input')
        assert error.value.error_code == code
        assert len(requests) == 2
        assert clients[0].timeout.read == 120 and clients[0].timeout.connect == 5
    finally:
        for client in clients:
            await client.close()


@pytest.mark.asyncio
async def test_search_http_returns_dimension_error_before_sql(config_store, sdk_transport, monkeypatch):
    import httpx
    from hub.core import search
    monkeypatch.setattr('shared.logger.configure_logging', lambda *a, **kw: None)
    from hub import main
    from hub.core.security import get_current_user
    monkeypatch.setitem(main.app.dependency_overrides, get_current_user, lambda: {'id': 'test-user'})
    _, behavior = sdk_transport
    behavior['embedding'] = [0.1] * 1024
    await settings.save_model_provider_config('llama_cpp', {'base_url': 'http://model.test/v1'})
    await settings.save_model_assignments([{'key': 'embedding', 'provider': 'llama_cpp', 'model': 'test'}])
    db = Mock(side_effect=AssertionError('No query SQL should run'))
    monkeypatch.setattr(search, 'AsyncSessionLocal', db)
    monkeypatch.setattr(main, 'AsyncSessionLocal', db)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=main.app), base_url='http://test') as client:
        response = await client.get('/api/search', params={'q': 'private query'})
    assert response.status_code == 502
    assert response.json()['error_code'] == ERR_EMBEDDING_DIMENSION_MISMATCH
    assert 'expected dimension 768' in response.json()['detail']
    assert 'actual dimension 1024' in response.json()['detail']
    db.assert_not_called()
