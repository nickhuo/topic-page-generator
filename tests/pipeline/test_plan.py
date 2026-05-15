import json
from pathlib import Path

import httpx
import respx

from generator.pipeline.plan import (
    AESTHETIC_CONFIDENCE_THRESHOLD,
    run_aesthetic_stage,
    run_plan_stage,
)
from generator.schema import EventFacts
from generator.llm.trace_buffer import drain, reset

FIX = Path(__file__).parent.parent / "fixtures"

_FACTS = EventFacts(
    entities=["GPT-5.5 Instant (OpenAI)"],
    what="OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT.",
    when="2026-05-01T00:00:00Z",
    supporting_sources=[],
)
_TITLE = "GPT-5.5 Instant rollout"


@respx.mock
async def test_plan_stage_calls_llm_and_returns_need_plan(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_plan_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await run_plan_stage(_FACTS, _TITLE)
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
    need_plan = await run_plan_stage(_FACTS, _TITLE)
    out = await run_aesthetic_stage(
        _FACTS, _TITLE, need_plan, evidence_preview="…sample evidence…"
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
    need_plan = await run_plan_stage(_FACTS, _TITLE)
    out = await run_aesthetic_stage(_FACTS, _TITLE, need_plan, evidence_preview="")
    assert out.preset_id == "reference"


def test_threshold_default():
    assert AESTHETIC_CONFIDENCE_THRESHOLD == 0.75


def test_infer_category_facts():
    from generator.pipeline.plan import infer_default_category

    assert infer_default_category(["infobox", "schedule"]) == "fact"


def test_infer_category_opinions():
    from generator.pipeline.plan import infer_default_category

    assert infer_default_category(["reactions"]) == "opinion"


def test_infer_category_mixed_falls_back_to_fact():
    from generator.pipeline.plan import infer_default_category

    assert infer_default_category(["reactions", "schedule"]) == "fact"


def test_infer_category_empty_is_none():
    from generator.pipeline.plan import infer_default_category

    assert infer_default_category([]) is None
