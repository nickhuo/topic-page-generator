"""Backbone planner: deterministic 6-section emitter."""

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
        supporting_sources=["s1"],
    )


def test_emits_six_backbone_sections_in_canonical_order():
    sections = build_backbone_sections(_facts(), canonical_title="NVIDIA GTC 2026")
    ids = [s.section_id for s in sections]
    assert ids == [
        "overview",
        "key_takeaways",
        "timeline",
        "key_facts",
        "background",
        "media_coverage",
    ]


def test_each_section_is_kind_backbone_with_unique_rank():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    assert all(s.kind == "backbone" for s in sections)
    ranks = [s.rank for s in sections]
    assert ranks == [1, 2, 3, 4, 5, 6]


def test_block_kind_mapping_matches_design():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    by_id = {s.section_id: s for s in sections}
    assert by_id["overview"].block_kind == "paragraph"
    assert by_id["key_takeaways"].block_kind == "paragraph"
    assert by_id["timeline"].block_kind == "timeline"
    assert by_id["key_facts"].block_kind == "factsheet"
    assert by_id["background"].block_kind == "paragraph"
    assert by_id["media_coverage"].block_kind == "newsfeed"


def test_each_section_has_nonempty_title_and_intent():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    for s in sections:
        assert s.title.strip(), f"empty title on {s.section_id}"
        assert s.intent.strip(), f"empty intent on {s.section_id}"


def test_acceptance_pulled_from_blockspec_default():
    from generator.blocks.specs import get_spec

    sections = build_backbone_sections(_facts(), canonical_title="t")
    for s in sections:
        spec_cls = get_spec(s.block_kind)
        # Backbone planner copies the spec's default_acceptance unless the
        # section needs a stricter variant. At minimum, description matches.
        assert s.acceptance.description == spec_cls.default_acceptance.description


def test_title_incorporates_canonical_title_for_overview():
    sections = build_backbone_sections(_facts(), canonical_title="NVIDIA GTC 2026")
    overview = next(s for s in sections if s.section_id == "overview")
    # Overview's intent should reference the event by canonical title.
    assert "NVIDIA GTC 2026" in overview.intent
