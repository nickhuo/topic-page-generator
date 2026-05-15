"""Research-query prompt builder — produces a Tavily query from section context."""

from __future__ import annotations

from generator.prompts.research_query import build_research_query_messages
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


def _section() -> SectionPlan:
    return SectionPlan(
        section_id="timeline",
        kind="backbone",
        title="Timeline",
        rank=3,
        block_kind="timeline",
        intent="3-7 milestones from announcement to keynote.",
        acceptance=AcceptanceCriteria(description="At least 3 milestone entries."),
    )


def test_initial_query_has_no_gap_context():
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        section=_section(),
        previous_gaps=None,
        previous_query=None,
    )
    user = msgs[1]["content"]
    assert "NVIDIA GTC 2026" in user
    assert "timeline" in user.lower()
    # No "previously tried" / "gap" block on first iteration
    assert "previous" not in user.lower()


def test_refine_query_includes_gaps_and_previous_query():
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        section=_section(),
        previous_gaps=["no source from before March 19"],
        previous_query="NVIDIA GTC 2026 announcements",
    )
    user = msgs[1]["content"]
    assert "no source from before March 19" in user
    assert "NVIDIA GTC 2026 announcements" in user


def test_output_format_directive_present():
    """The prompt must instruct the LLM to output a bare Tavily query string."""
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="t",
        section=_section(),
        previous_gaps=None,
        previous_query=None,
    )
    system = msgs[0]["content"]
    assert "query" in system.lower()
    assert "json" in system.lower() or "string" in system.lower()
