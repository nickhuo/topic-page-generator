"""Tests for the where_to_watch module: schema binding, render gate, registry."""
from generator.modules import MODULE_REGISTRY
from generator.modules.where_to_watch import WhereToWatchModule
from generator.schema import WhereToWatchData, WhereToWatchChannel


def test_where_to_watch_registered():
    assert MODULE_REGISTRY["where_to_watch"] is WhereToWatchModule


def test_where_to_watch_metadata():
    assert WhereToWatchModule.kind == "where_to_watch"
    assert WhereToWatchModule.serves_needs == ["what_can_do"]
    assert "ChannelList" in WhereToWatchModule.allowed_artifacts
    assert WhereToWatchModule.data_schema is WhereToWatchData
    assert isinstance(WhereToWatchModule.extraction_prompt_template, str)
    assert "{primary_entity}" in WhereToWatchModule.extraction_prompt_template
    assert "{evidence_block}" in WhereToWatchModule.extraction_prompt_template


def _make_channel() -> WhereToWatchChannel:
    return WhereToWatchChannel(type="streaming", name="ESPN+", source_id="s1")


def test_where_to_watch_should_render():
    data = WhereToWatchData(channels=[_make_channel()])
    assert WhereToWatchModule().should_render(data)


def test_where_to_watch_should_not_render_empty():
    data = WhereToWatchData(channels=[])
    assert not WhereToWatchModule().should_render(data)


def test_where_to_watch_should_render_none():
    assert not WhereToWatchModule().should_render(None)
