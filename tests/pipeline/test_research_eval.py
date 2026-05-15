"""Research-eval stage — LLM judge over a section's evidence pool."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from generator.llm.trace_buffer import reset
from generator.pipeline.research_eval import run_research_eval_stage
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    ResearchEvalResult,
    SectionPlan,
    Source,
    SourceRights,
)

FIX = Path(__file__).parent.parent / "fixtures"


def _section() -> SectionPlan:
    return SectionPlan(
        section_id="overview",
        kind="backbone",
        title="Overview",
        rank=1,
        block_kind="paragraph",
        intent="two paragraphs framing the event",
        acceptance=AcceptanceCriteria(description="who/what/when covered"),
    )


def _sources() -> list[Source]:
    return [
        Source(
            id="s1",
            url="https://reuters.com/a",
            publisher=Publisher(name="Reuters", tier="T1"),
            title="Headline",
            published_at="2026-03-19T12:00:00Z",
            fetched_at="2026-03-19T13:00:00Z",
            language="en",
            rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
            summary="Reuters reports on NVIDIA's GTC keynote.",
        ),
    ]


@respx.mock
async def test_eval_returns_satisfied(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_research_eval_satisfied.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await run_research_eval_stage(
        section=_section(), sources=_sources(), canonical_title="t"
    )
    assert isinstance(result, ResearchEvalResult)
    assert result.satisfied is True


@respx.mock
async def test_eval_returns_unsatisfied_with_gap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_research_eval_needs_more.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await run_research_eval_stage(
        section=_section(), sources=_sources(), canonical_title="t"
    )
    assert result.satisfied is False
    assert len(result.gaps) >= 1
    assert result.next_query_hint
