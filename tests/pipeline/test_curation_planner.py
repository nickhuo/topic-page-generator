"""Curation planner stage — one LLM call producing 0-4 curated SectionPlans."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from generator.llm.trace_buffer import reset
from generator.pipeline.curation_planner import run_curation_stage
from generator.schema import (
    AcceptanceCriteria,
    EventFacts,
    SectionPlan,
    SectionPlanOutput,
)

FIX = Path(__file__).parent.parent / "fixtures"


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


@respx.mock
async def test_curation_stage_returns_section_plan_output(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_curation_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await run_curation_stage(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        backbone=_backbone(),
    )
    assert isinstance(out, SectionPlanOutput)
    assert all(s.kind == "curated" for s in out.sections)


@respx.mock
async def test_curation_stage_records_llm_call(monkeypatch):
    from generator.llm.trace_buffer import drain

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_curation_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    await run_curation_stage(facts=_facts(), canonical_title="t", backbone=_backbone())
    calls = drain()
    assert len(calls) == 1
    # Stage attribution happens at TraceRecorder layer, not on LLMCall itself.
    # We only verify the call was made and the model is the curation default.
    assert calls[0].model == "anthropic/claude-sonnet-4-6"


async def test_curation_stage_returns_empty_when_llm_returns_empty(monkeypatch):
    """An LLM that says "no curated sections needed" must produce an empty
    SectionPlanOutput, not a crash."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    empty_envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-sonnet-4-6",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": '{"sections":[]}'},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
    }
    with respx.mock:
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=empty_envelope)
        )
        out = await run_curation_stage(
            facts=_facts(), canonical_title="t", backbone=_backbone()
        )
    assert out.sections == []
