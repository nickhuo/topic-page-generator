"""Tests for blocks.converter.module_to_block.

Each module kind has a natural BlockKind that `module_to_block` adapts it
into. We exercise both the default path and one render_override path.
"""

from __future__ import annotations

from generator.blocks import default_block_kind, module_to_block
from generator.blocks.schema import (
    ChartBlockData,
    FactsheetBlockData,
    MapBlockData,
    NewsfeedBlockData,
    ParagraphBlockData,
    ReactionsBlock,
    TimelineBlockData,
)
from tests.fixtures import make_full_event_page


def _by_kind(modules, kind: str):
    return next(m for m in modules if m.kind == kind)


def test_default_block_kind_map_is_total():
    """Every kind on a fully populated page resolves to a known block kind."""
    page = make_full_event_page()
    for m in page.modules:
        bk = default_block_kind(m.kind)
        assert bk in {
            "paragraph",
            "timeline",
            "chart",
            "newsfeed",
            "factsheet",
            "map",
            "reactions",
        }


def test_background_renders_paragraph():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "background"), page.sources)
    assert isinstance(block, ParagraphBlockData)
    assert block.paragraphs_md  # non-empty


def test_infobox_renders_factsheet():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "infobox"), page.sources)
    assert isinstance(block, FactsheetBlockData)
    assert len(block.rows) >= 1


def test_schedule_renders_timeline():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "schedule"), page.sources)
    assert isinstance(block, TimelineBlockData)
    assert all(e.time for e in block.entries)


def test_changelog_renders_timeline_with_importance():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "changelog"), page.sources)
    assert isinstance(block, TimelineBlockData)
    importances = {e.importance for e in block.entries}
    # Changelog fixture has both "feature" and "breaking" entries
    assert importances & {"feature", "breaking"}


def test_kpi_numbers_renders_chart_stat():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "kpi_numbers"), page.sources)
    assert isinstance(block, ChartBlockData)
    assert block.chart_type == "stat"
    assert block.stats and len(block.stats) >= 1


def test_comparison_renders_chart_compare_table():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "comparison"), page.sources)
    assert isinstance(block, ChartBlockData)
    assert block.chart_type == "compare_table"
    assert block.table is not None
    assert len(block.table.subjects) >= 2


def test_media_coverage_renders_newsfeed():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "media_coverage"), page.sources)
    assert isinstance(block, NewsfeedBlockData)
    assert block.variant == "news"
    assert block.cards


def test_reactions_renders_reactions_block():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "reactions"), page.sources)
    assert isinstance(block, ReactionsBlock)
    assert block.cards
    assert len(block.cards) <= 4


def test_official_statements_default_renders_newsfeed_quotes():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "official_statements"), page.sources)
    assert isinstance(block, NewsfeedBlockData)
    assert block.variant == "quotes"


def test_where_to_watch_renders_newsfeed_channels():
    page = make_full_event_page()
    block = module_to_block(_by_kind(page.modules, "where_to_watch"), page.sources)
    assert isinstance(block, NewsfeedBlockData)
    assert block.variant == "channels"


def test_render_override_schedule_as_map():
    page = make_full_event_page()
    block = module_to_block(
        _by_kind(page.modules, "schedule"), page.sources, override="map"
    )
    assert isinstance(block, MapBlockData)
    assert block.locations


def test_render_override_official_statements_as_paragraph():
    page = make_full_event_page()
    block = module_to_block(
        _by_kind(page.modules, "official_statements"),
        page.sources,
        override="paragraph",
    )
    assert isinstance(block, ParagraphBlockData)
    # Each statement should have produced both a paragraph and a pull quote
    assert block.paragraphs_md
    assert block.pull_quotes
