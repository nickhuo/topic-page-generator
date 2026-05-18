"""Tests for the editor-triggered section proposer."""

from __future__ import annotations

import pytest

from generator.pipeline.section_proposer import _ProposedSection, propose_section
from generator.schema import (
    AcceptanceCriteria,
    EventFacts,
    SectionPlan,
)


def _facts():
    return EventFacts(
        entities=["Acme"],
        what="something",
        when="2026-05-14T00:00:00+00:00",
        supporting_sources=["s1"],
    )


def _plan(section_id: str, rank: int = 5):
    return SectionPlan(
        section_id=section_id,
        kind="curated",
        title=section_id,
        rank=rank,
        block_kind="paragraph",
        intent="x",
        acceptance=AcceptanceCriteria(description="ok"),
    )


@pytest.mark.asyncio
async def test_propose_section_assigns_next_rank_and_curated(monkeypatch) -> None:
    async def fake_call_structured(*, model, messages, response_model):
        return _ProposedSection(
            section_id="sponsor_reactions",
            title="Sponsor reactions",
            block_kind="reactions",
            intent="Capture sponsor sentiment.",
            acceptance=AcceptanceCriteria(description="≥2 sponsor quotes"),
        )

    monkeypatch.setattr(
        "generator.pipeline.section_proposer.call_structured", fake_call_structured
    )
    existing = [_plan("overview", rank=1), _plan("kpi_dashboard", rank=5)]
    out = await propose_section(
        "I want sponsor reactions",
        facts=_facts(),
        canonical_title="Acme launch",
        existing_sections=existing,
    )
    assert out.kind == "curated"
    assert out.placement == "main"
    assert out.section_id == "sponsor_reactions"
    assert out.rank == 6
    assert out.block_kind == "reactions"


@pytest.mark.asyncio
async def test_propose_section_dedupes_section_id(monkeypatch) -> None:
    async def fake_call_structured(*, model, messages, response_model):
        return _ProposedSection(
            section_id="kpi_dashboard",  # collides
            title="Another KPI",
            block_kind="chart",
            intent="More KPIs.",
            acceptance=AcceptanceCriteria(description="≥1 chart"),
        )

    monkeypatch.setattr(
        "generator.pipeline.section_proposer.call_structured", fake_call_structured
    )
    existing = [_plan("kpi_dashboard", rank=5)]
    out = await propose_section(
        "more KPIs",
        facts=_facts(),
        canonical_title="t",
        existing_sections=existing,
    )
    assert out.section_id == "kpi_dashboard_2"


@pytest.mark.asyncio
async def test_propose_section_rewrites_forbidden_block_kind(monkeypatch) -> None:
    async def fake_call_structured(*, model, messages, response_model):
        return _ProposedSection(
            section_id="extra_timeline",
            title="Extra",
            block_kind="timeline",  # forbidden for curation
            intent="x",
            acceptance=AcceptanceCriteria(description="ok"),
        )

    monkeypatch.setattr(
        "generator.pipeline.section_proposer.call_structured", fake_call_structured
    )
    out = await propose_section(
        "x",
        facts=_facts(),
        canonical_title="t",
        existing_sections=[],
    )
    assert out.block_kind == "paragraph"
