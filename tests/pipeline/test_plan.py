import json
from pathlib import Path

import httpx
import respx

from generator.pipeline.plan import (
    AESTHETIC_CONFIDENCE_THRESHOLD,
    run_aesthetic_stage,
    run_plan_stage,
)
from generator.schema import (
    DisambiguationChosen,
    DisambiguationOutput,
    TriageOutput,
)
from generator.llm.trace_buffer import drain, reset

FIX = Path(__file__).parent.parent / "fixtures"

_TRIAGE = TriageOutput(
    is_event=True,
    primary_entity="GPT-5.5 Instant (OpenAI)",
    event_type_hint="product_launch",
    temporal_posture="recent",
    confidence=0.92,
    alternatives=[],
    reasoning="x",
)
_DISAMB = DisambiguationOutput(
    resolved=True,
    chosen=DisambiguationChosen(
        entity="GPT-5.5 Instant (OpenAI)",
        event_type_hint="product_launch",
        time_anchor="2026-05-01T00:00:00Z",
        supporting_sources=[],
    ),
    unresolved_candidates=[],
)


@respx.mock
async def test_plan_stage_calls_llm_and_returns_need_plan(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_plan_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await run_plan_stage(_TRIAGE, _DISAMB)
    assert out.layout_preset_id == "product_focus"
    assert len(out.need_plans) == 8
    # rank is a permutation of 1..8
    assert sorted(p.rank for p in out.need_plans) == list(range(1, 9))
    activated = [p for p in out.need_plans if p.activated]
    assert len(activated) >= 4
    # Section titles are event-specific, not the literal need names.
    what_happened = next(p for p in out.need_plans if p.need_id == "what_happened")
    assert "GPT-5.5" in what_happened.section_title
    assert len(drain()) == 1


@respx.mock
async def test_aesthetic_happy_path(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    plan_payload = json.loads((FIX / "openrouter_plan_happy.json").read_text())
    aesth_payload = json.loads((FIX / "openrouter_aesthetic_happy.json").read_text())
    # First call hits plan, second hits aesthetic.
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=plan_payload),
            httpx.Response(200, json=aesth_payload),
        ]
    )
    need_plan = await run_plan_stage(_TRIAGE, _DISAMB)
    out = await run_aesthetic_stage(
        _TRIAGE, need_plan, evidence_preview="…sample evidence…"
    )
    assert out.preset_id == "product_focus"
    assert out.preset_confidence == 0.88
    assert out.aesthetic_overrides.palette == "minimal_tech"


@respx.mock
async def test_aesthetic_falls_back_to_reference_when_low_confidence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    plan_payload = json.loads((FIX / "openrouter_plan_happy.json").read_text())
    aesth_payload = json.loads((FIX / "openrouter_aesthetic_happy.json").read_text())
    inner = json.loads(aesth_payload["choices"][0]["message"]["content"])
    inner["preset_confidence"] = 0.55
    aesth_payload["choices"][0]["message"]["content"] = json.dumps(inner)
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=plan_payload),
            httpx.Response(200, json=aesth_payload),
        ]
    )
    need_plan = await run_plan_stage(_TRIAGE, _DISAMB)
    out = await run_aesthetic_stage(_TRIAGE, need_plan, evidence_preview="")
    assert out.preset_id == "reference"


def test_threshold_default():
    assert AESTHETIC_CONFIDENCE_THRESHOLD == 0.75
