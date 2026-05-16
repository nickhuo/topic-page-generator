"""Backbone planner: deterministic 4-section emitter with placement."""

from __future__ import annotations

from generator.pipeline.backbone_planner import build_backbone_sections
from generator.schema import EventFacts


def _facts() -> EventFacts:
    return EventFacts(
        entities=["NVIDIA", "GTC 2026"],
        what="NVIDIA announces new GPU architecture at GTC.",
        when="2026-03-19T14:00:00-07:00",
        where="San Jose, CA",
        why="Generation leap in AI compute capacity.",
        subtitle="NVIDIA unveils a new GPU architecture at GTC 2026 in San Jose.",
        supporting_sources=["s1"],
    )


def test_emits_four_backbone_sections_in_canonical_order():
    sections = build_backbone_sections(_facts(), canonical_title="NVIDIA GTC 2026")
    ids = [s.section_id for s in sections]
    assert ids == [
        "overview",
        "timeline",
        "media_coverage",
        "latest_news",
    ]


def test_each_section_is_kind_backbone_with_unique_rank():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    assert all(s.kind == "backbone" for s in sections)
    ranks = [s.rank for s in sections]
    assert ranks == [1, 2, 3, 4]


def test_block_kind_mapping_matches_design():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    by_id = {s.section_id: s for s in sections}
    assert by_id["overview"].block_kind == "paragraph"
    assert by_id["timeline"].block_kind == "timeline"
    assert by_id["media_coverage"].block_kind == "newsfeed"
    assert by_id["latest_news"].block_kind == "latest_news"


def test_placement_routes_timeline_to_sidebar():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    by_id = {s.section_id: s for s in sections}
    assert by_id["overview"].placement == "main"
    assert by_id["timeline"].placement == "sidebar"
    assert by_id["media_coverage"].placement == "main"
    assert by_id["latest_news"].placement == "main"


def test_each_section_has_nonempty_title_and_intent():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    for s in sections:
        assert s.title.strip(), f"empty title on {s.section_id}"
        assert s.intent.strip(), f"empty intent on {s.section_id}"


def test_timeline_acceptance_requires_all_three_phases():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    timeline = next(s for s in sections if s.section_id == "timeline")
    assert set(timeline.acceptance.required_facets) >= {"past", "present", "future"}


def test_media_coverage_acceptance_requires_thumbnails():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    mc = next(s for s in sections if s.section_id == "media_coverage")
    assert "thumbnail_url" in mc.acceptance.required_facets


def test_title_incorporates_canonical_title_for_overview():
    sections = build_backbone_sections(_facts(), canonical_title="NVIDIA GTC 2026")
    overview = next(s for s in sections if s.section_id == "overview")
    assert "NVIDIA GTC 2026" in overview.intent


def test_latest_news_acceptance_requires_published_at():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    ln = next(s for s in sections if s.section_id == "latest_news")
    assert "published_at" in ln.acceptance.required_facets


def test_latest_news_and_media_coverage_intents_diverge():
    """The two news-card backbone sections must be linguistically distinct
    so research_query and block_extract LLMs treat them differently."""
    sections = build_backbone_sections(_facts(), canonical_title="t")
    mc = next(s for s in sections if s.section_id == "media_coverage").intent.lower()
    ln = next(s for s in sections if s.section_id == "latest_news").intent.lower()

    # latest_news leans on chronology
    assert "chronological" in ln
    assert "published_at" in ln

    # media_coverage leans on editorial picks / featured / top
    assert ("featured" in mc) or ("top" in mc)

    # And they shouldn't be the same blob.
    assert mc != ln
