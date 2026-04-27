from types import SimpleNamespace

from worker.plugins.runtime import build_item_raw_data, fallback_text_for_summary, resolve_sync_fetch_mode


def test_build_summary_raw_data_preserves_generic_item_fields():
    item = SimpleNamespace(
        id="item-1",
        title="Example",
        raw_link="https://example.com/post",
        source_type="custom_plugin",
        intent="article",
        content_text="Stored content",
        summary="Stored summary",
        metadata_extra={"foo": "bar"},
    )

    raw_data = build_item_raw_data(item)

    assert raw_data["id"] == "item-1"
    assert raw_data["title"] == "Example"
    assert raw_data["raw_link"] == "https://example.com/post"
    assert raw_data["url"] == "https://example.com/post"
    assert raw_data["source_type"] == "custom_plugin"
    assert raw_data["description"] == "Stored content"
    assert raw_data["metadata_extra"] == {"foo": "bar"}


def test_build_summary_raw_data_adds_github_owner_shape():
    item = SimpleNamespace(
        id="item-1",
        title="Repo title",
        raw_link="https://github.com/openai/example",
        source_type="github_star",
        intent="article",
        content_text="Repo description",
        summary="",
        metadata_extra={},
    )

    raw_data = build_item_raw_data(item)

    assert raw_data["owner"] == {"login": "openai"}
    assert raw_data["name"] == "example"


def test_fallback_text_for_summary_uses_stored_content():
    item = SimpleNamespace(title="Example", content_text="Body", summary="Summary")

    assert fallback_text_for_summary(item) == "标题：Example\n\n简介：Body"


def test_manual_incremental_sync_uses_full_fetch_and_disables_breaker():
    fetch_mode, breaker_disabled = resolve_sync_fetch_mode(
        incremental_ai_sync=True,
        sync_mode="manual",
        has_existing_items=True,
    )

    assert fetch_mode == "full"
    assert breaker_disabled is True


def test_auto_incremental_first_sync_uses_full_fetch_and_disables_breaker():
    fetch_mode, breaker_disabled = resolve_sync_fetch_mode(
        incremental_ai_sync=True,
        sync_mode="auto",
        has_existing_items=False,
    )

    assert fetch_mode == "full"
    assert breaker_disabled is True


def test_auto_incremental_existing_sync_uses_latest_fetch_and_keeps_breaker():
    fetch_mode, breaker_disabled = resolve_sync_fetch_mode(
        incremental_ai_sync=True,
        sync_mode="auto",
        has_existing_items=True,
    )

    assert fetch_mode == "latest"
    assert breaker_disabled is False
