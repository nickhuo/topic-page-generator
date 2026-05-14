import json
from pathlib import Path

import httpx
import respx

from generator.pipeline.disambiguate import run, CONFIDENCE_THRESHOLD
from generator.schema import TriageOutput, TriageAlternative
from generator.llm.trace_buffer import drain, reset

FIX = Path(__file__).parent.parent / "fixtures"


async def test_disambiguate_short_circuits_when_confident():
    """Triage confidence above threshold → no LLM call, return derived chosen."""
    reset()
    triage = TriageOutput(
        is_event=True,
        primary_entity="GPT-5.5 Instant (OpenAI)",
        event_type_hint="product_launch",
        temporal_posture="recent",
        time_anchor="2026-05-01T00:00:00Z",
        confidence=0.93,
        alternatives=[],
        reasoning="x",
    )
    out = await run(triage)
    assert out.resolved is True
    assert out.chosen.entity == "GPT-5.5 Instant (OpenAI)"
    # no LLM call was made
    assert drain() == []


@respx.mock
async def test_disambiguate_fires_llm_when_low_confidence(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    # Stub: return a non-empty Source so the LLM call fires.
    async def fake_tavily(*a, **kw):
        from generator.schema import Publisher, Source, SourceRights
        return [Source(
            id="src_abc123",
            url="https://example.com/apollo",
            publisher=Publisher(name="Example", tier="T1"),
            title="Apollo line launch",
            published_at="2026-05-13T00:00:00Z",
            fetched_at="2026-05-13T12:00:00Z",
            language="en",
            rights=SourceRights(max_excerpt_words=30, can_paraphrase=False),
        )]
    monkeypatch.setattr("generator.pipeline.disambiguate.fetch_tavily", fake_tavily)

    payload = json.loads((FIX / "openrouter_disambiguate_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    triage = TriageOutput(
        is_event=True,
        primary_entity="Apollo program",
        event_type_hint="generic_event",
        temporal_posture="recent",
        confidence=0.40,
        alternatives=[
            TriageAlternative(entity="Apollo (SpaceX merch line)", event_type_hint="product_launch", rationale="r"),
            TriageAlternative(entity="Apollo program (NASA)", event_type_hint="generic_event", rationale="r"),
        ],
        reasoning="x",
    )
    out = await run(triage)
    assert out.resolved is True
    assert out.chosen.entity == "Apollo (SpaceX merch line)"
    assert len(drain()) == 1


def test_threshold_default():
    assert CONFIDENCE_THRESHOLD == 0.85
