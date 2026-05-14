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


def test_plan_stage_is_deterministic_lookup():
    out = run_plan_stage(_TRIAGE, _DISAMB)
    assert out.archetype_hint == "product_launch"
    assert out.layout_preset_id == "product_focus"


def test_plan_stage_falls_through_for_unknown_type():
    triage = _TRIAGE.model_copy(update={"event_type_hint": "weird_thing"})
    out = run_plan_stage(triage, _DISAMB)
    assert out.archetype_hint == "generic_event"


@respx.mock
async def test_aesthetic_happy_path(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_aesthetic_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    plan = run_plan_stage(_TRIAGE, _DISAMB)
    out = await run_aesthetic_stage(_TRIAGE, plan, evidence_preview="…sample evidence…")
    assert out.preset_id == "product_focus"
    assert out.preset_confidence == 0.88
    assert out.aesthetic_overrides.palette == "minimal_tech"
    assert len(drain()) == 1


@respx.mock
async def test_aesthetic_falls_back_to_reference_when_low_confidence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_aesthetic_happy.json").read_text())
    inner = json.loads(payload["choices"][0]["message"]["content"])
    inner["preset_confidence"] = 0.55
    payload["choices"][0]["message"]["content"] = json.dumps(inner)
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    plan = run_plan_stage(_TRIAGE, _DISAMB)
    out = await run_aesthetic_stage(_TRIAGE, plan, evidence_preview="")
    assert out.preset_id == "reference"  # fallback applied


def test_threshold_default():
    assert AESTHETIC_CONFIDENCE_THRESHOLD == 0.75
