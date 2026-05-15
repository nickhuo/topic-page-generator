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
        "background",
        "media_coverage",
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
    assert by_id["background"].block_kind == "paragraph"
    assert by_id["media_coverage"].block_kind == "newsfeed"


def test_placement_routes_timeline_and_background_to_sidebar():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    by_id = {s.section_id: s for s in sections}
    assert by_id["overview"].placement == "main"
    assert by_id["timeline"].placement == "sidebar"
    assert by_id["background"].placement == "sidebar"
    assert by_id["media_coverage"].placement == "main"


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
