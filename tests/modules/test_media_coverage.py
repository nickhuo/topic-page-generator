"""Tests for the media_coverage module: schema binding, render gate, registry."""

from generator.modules import MODULE_REGISTRY
from generator.modules.media_coverage import MediaCoverageModule
from generator.schema import MediaCoverageData, MediaCoverageItem


def test_media_coverage_registered():
    assert MODULE_REGISTRY["media_coverage"] is MediaCoverageModule


def test_media_coverage_metadata():
    assert MediaCoverageModule.kind == "media_coverage"
    assert "world_reaction" in MediaCoverageModule.serves_needs
    assert "current_state" in MediaCoverageModule.serves_needs
    assert "CoverageList" in MediaCoverageModule.allowed_artifacts
    assert MediaCoverageModule.data_schema is MediaCoverageData
    assert isinstance(MediaCoverageModule.extraction_prompt_template, str)
    assert "{title}" in MediaCoverageModule.extraction_prompt_template
    assert "{evidence_block}" in MediaCoverageModule.extraction_prompt_template


def _make_item(n: int = 0) -> MediaCoverageItem:
    return MediaCoverageItem(
        headline=f"Headline {n}",
        publisher="The Times",
        publisher_tier="T1",
        published_at="2025-01-01T00:00:00Z",
        url="https://example.com/article",
        snippet="Short snippet here.",
        source_id=f"s{n}",
    )


def test_media_coverage_should_render():
    data = MediaCoverageData(
        items=[_make_item(i) for i in range(3)], grouping_strategy="flat"
    )
    assert MediaCoverageModule().should_render(data)


def test_media_coverage_should_not_render_too_few():
    data = MediaCoverageData(
        items=[_make_item(i) for i in range(2)], grouping_strategy="flat"
    )
    assert not MediaCoverageModule().should_render(data)


def test_media_coverage_should_render_none():
    assert not MediaCoverageModule().should_render(None)
