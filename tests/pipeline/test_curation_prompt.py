"""Curation prompt builder."""

from __future__ import annotations

from generator.prompts.curation import build_curation_messages
from generator.schema import (
    AcceptanceCriteria,
    EventFacts,
    SectionPlan,
)


def _facts() -> EventFacts:
    return EventFacts(
        entities=["NVIDIA"],
        what="GTC 2026 keynote",
        when="2026-03-19",
        where="San Jose",
        why="New architecture",
        supporting_sources=["s1"],
    )


def _backbone() -> list[SectionPlan]:
    return [
        SectionPlan(
            section_id="overview",
            kind="backbone",
            title="Overview",
            rank=1,
            block_kind="paragraph",
            intent="i",
            acceptance=AcceptanceCriteria(description="d"),
        )
    ]


def test_returns_system_and_user_messages():
    msgs = build_curation_messages(
        facts=_facts(), canonical_title="NVIDIA GTC 2026", backbone=_backbone()
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_system_message_lists_curated_block_kinds():
    msgs = build_curation_messages(
        facts=_facts(), canonical_title="t", backbone=_backbone()
    )
    system = msgs[0]["content"]
    for kind in [
        "paragraph", "chart", "newsfeed", "reactions", "gallery",
    ]:
        assert kind in system, f"block kind {kind} missing from prompt"
    # timeline is mentioned in the FORBIDDEN section
    assert "timeline" in system
    assert "FORBIDDEN" in system


def test_user_payload_includes_facts_and_already_chosen_sections():
    msgs = build_curation_messages(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        backbone=_backbone(),
    )
    user = msgs[1]["content"]
    assert "NVIDIA GTC 2026" in user
    assert "overview" in user  # already-chosen section listed


def test_system_message_bounds_curated_count_zero_to_four():
    msgs = build_curation_messages(
        facts=_facts(), canonical_title="t", backbone=_backbone()
    )
    system = msgs[0]["content"]
    # The prompt must state the allowed count range so the LLM can't run away.
    assert "0" in system and "4" in system
