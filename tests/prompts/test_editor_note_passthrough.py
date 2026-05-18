"""Verify editor_note kwarg lands in both research_query and block_extract prompts."""

from __future__ import annotations

from generator.prompts.block_extract import build_block_extract_messages
from generator.prompts.research_query import build_research_query_messages
from generator.schema import AcceptanceCriteria, EventFacts, SectionPlan


def _facts() -> EventFacts:
    return EventFacts(
        entities=["E"],
        what="w",
        when="2026-05-14T00:00:00+00:00",
        supporting_sources=["s"],
    )


def _section() -> SectionPlan:
    return SectionPlan(
        section_id="sec",
        kind="curated",
        title="Sec",
        rank=5,
        block_kind="paragraph",
        intent="intent",
        acceptance=AcceptanceCriteria(description="ok"),
    )


def test_research_query_includes_editor_note() -> None:
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="Canonical",
        section=_section(),
        previous_gaps=None,
        previous_query=None,
        editor_note="Focus on financial impact.",
    )
    user = msgs[1]["content"]
    assert "editor_note" in user
    assert "Focus on financial impact." in user


def test_research_query_omits_editor_note_when_none() -> None:
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="Canonical",
        section=_section(),
        previous_gaps=None,
        previous_query=None,
    )
    assert "editor_note" not in msgs[1]["content"]


def test_block_extract_includes_editor_note() -> None:
    from generator.blocks.specs import get_spec

    spec_cls = get_spec("paragraph")
    msgs = build_block_extract_messages(
        section=_section(),
        spec=spec_cls,
        sources=[],
        canonical_title="Canonical",
        editor_note="Use plain language.",
    )
    user = msgs[1]["content"]
    assert "EDITOR_NOTE: Use plain language." in user


def test_block_extract_omits_editor_note_when_none() -> None:
    from generator.blocks.specs import get_spec

    spec_cls = get_spec("paragraph")
    msgs = build_block_extract_messages(
        section=_section(),
        spec=spec_cls,
        sources=[],
        canonical_title="Canonical",
    )
    assert "EDITOR_NOTE" not in msgs[1]["content"]
