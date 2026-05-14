import json
from pathlib import Path

import httpx
import pytest
import respx

from generator.llm.client import call_structured, LLMConfigError
from generator.llm.trace_buffer import drain, reset
from generator.schema import TriageOutput

FIX = Path(__file__).parent.parent / "fixtures"


@respx.mock
async def test_call_structured_happy_path(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_triage_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await call_structured(
        model="anthropic/claude-haiku-4-5",
        messages=[{"role": "user", "content": "hi"}],
        response_model=TriageOutput,
    )
    assert isinstance(out, TriageOutput)
    assert out.confidence == 0.92
    calls = drain()
    assert len(calls) == 1
    assert calls[0].input_tokens == 412
    assert calls[0].output_tokens == 87


@respx.mock
async def test_call_structured_retries_on_5xx(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_triage_happy.json").read_text())
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(200, json=payload),
        ]
    )
    out = await call_structured(
        model="anthropic/claude-haiku-4-5",
        messages=[{"role": "user", "content": "hi"}],
        response_model=TriageOutput,
    )
    assert out.confidence == 0.92
    assert route.call_count == 2


@respx.mock
async def test_call_structured_clamps_overflow_floats(monkeypatch):
    """LLM emits confidence=1.0001; client clamps to 1.0 before Pydantic."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    bad = json.loads((FIX / "openrouter_triage_happy.json").read_text())
    inner = json.loads(bad["choices"][0]["message"]["content"])
    inner["confidence"] = 1.0001
    bad["choices"][0]["message"]["content"] = json.dumps(inner)
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=bad)
    )
    out = await call_structured(
        model="anthropic/claude-haiku-4-5",
        messages=[{"role": "user", "content": "hi"}],
        response_model=TriageOutput,
    )
    assert out.confidence == 1.0


@respx.mock
async def test_call_structured_retries_on_validation_error(monkeypatch):
    """First reply has wrong type; second reply is valid; one retry exhausted."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    bad = json.loads((FIX / "openrouter_triage_happy.json").read_text())
    inner = json.loads(bad["choices"][0]["message"]["content"])
    inner["confidence"] = "very-high"  # wrong type
    bad_payload = {**bad, "choices": [{"index": 0, "message": {"role": "assistant", "content": json.dumps(inner)}, "finish_reason": "stop"}]}
    good = json.loads((FIX / "openrouter_triage_happy.json").read_text())
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=[
            httpx.Response(200, json=bad_payload),
            httpx.Response(200, json=good),
        ]
    )
    out = await call_structured(
        model="anthropic/claude-haiku-4-5",
        messages=[{"role": "user", "content": "hi"}],
        response_model=TriageOutput,
    )
    assert out.confidence == 0.92
    assert route.call_count == 2


def test_missing_api_key_raises(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(LLMConfigError):
        # constructor / first call should fail clearly
        import asyncio
        asyncio.run(call_structured(
            model="m", messages=[{"role": "user", "content": "x"}], response_model=TriageOutput
        ))
