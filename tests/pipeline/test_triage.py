import json
from pathlib import Path

import httpx
import respx

from generator.pipeline.triage import run
from generator.llm.trace_buffer import drain, reset

FIX = Path(__file__).parent.parent / "fixtures"


@respx.mock
async def test_triage_happy_path(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_triage_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await run(
        "OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT in May 2026"
    )
    assert out.primary_entity == "GPT-5.5 Instant (OpenAI)"
    assert out.event_type_hint == "product_launch"
    assert out.confidence == 0.92
    # LLM call recorded
    assert len(drain()) == 1


@respx.mock
async def test_triage_low_confidence_passes_through(monkeypatch):
    """Low-confidence LLM output is not modified; downstream gates decide."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_triage_happy.json").read_text())
    inner = json.loads(payload["choices"][0]["message"]["content"])
    inner["confidence"] = 0.40
    inner["alternatives"] = [
        {"entity": "X1", "event_type_hint": "generic_event", "rationale": "first"},
        {"entity": "X2", "event_type_hint": "generic_event", "rationale": "second"},
    ]
    payload["choices"][0]["message"]["content"] = json.dumps(inner)
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await run("Some ambiguous sentence")
    assert out.confidence == 0.40
    assert len(out.alternatives) == 2
