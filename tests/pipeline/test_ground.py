"""Tests for the merged ground stage."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from generator.llm.trace_buffer import drain, reset
from generator.pipeline import ground
from generator.schema import Publisher, Source, SourceRights

FIX = Path(__file__).parent.parent / "fixtures"


def _source(sid: str = "src_a1") -> Source:
    return Source(
        id=sid,
        url=f"https://reuters.com/{sid}",
        publisher=Publisher(name="Reuters", tier="T0"),
        title="Test article",
        published_at="2026-05-14T08:00:00Z",
        fetched_at="2026-05-14T09:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=10000, can_paraphrase=True),
    )


@respx.mock
async def test_ground_hot_event(monkeypatch):
    """Fresh Tavily evidence → is_hot_event=True with grounded EventFacts."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tav-test")
    reset()

    # Stub Tavily to return a single fresh source.
    async def fake_fetch_tavily(query, time_range_days, max_results=10, **kw):
        return [_source("src_a1")]

    monkeypatch.setattr(ground, "fetch_tavily", fake_fetch_tavily)

    payload = json.loads((FIX / "openrouter_ground_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )

    out = await ground.run("OpenAI rolled out GPT-5.5 Instant")
    assert out.is_hot_event is True
    assert out.facts is not None
    assert out.facts.entities == ["GPT-5.5 Instant (OpenAI)"]
    assert out.facts.when == "2026-05-01T00:00:00Z"
    assert out.canonical_title == "GPT-5.5 Instant rollout"
    assert len(drain()) == 1


@respx.mock
async def test_ground_evergreen_query_rejected(monkeypatch):
    """Zero/evergreen Tavily evidence → is_hot_event=False with rejection_reason."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tav-test")
    reset()

    async def fake_fetch_tavily(query, time_range_days, max_results=10, **kw):
        return []

    monkeypatch.setattr(ground, "fetch_tavily", fake_fetch_tavily)

    not_hot_payload = {
        "id": "gen-evergreen",
        "model": "anthropic/claude-sonnet-4-6",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "is_hot_event": False,
                            "rejection_reason": "No fresh sources; query reads as evergreen.",
                            "facts": None,
                            "canonical_title": None,
                            "confidence": 0.97,
                            "reasoning": "How-to question, not a news event.",
                        }
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 40, "total_tokens": 240},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=not_hot_payload)
    )

    out = await ground.run("Explain how Python decorators work")
    assert out.is_hot_event is False
    assert out.facts is None
    assert "evergreen" in (out.rejection_reason or "").lower()


@respx.mock
async def test_ground_multi_actor_event(monkeypatch):
    """Multi-actor event returns multiple entities in canonical order."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tav-test")
    reset()

    async def fake_fetch_tavily(query, time_range_days, max_results=10, **kw):
        return [_source("src_x1"), _source("src_x2")]

    monkeypatch.setattr(ground, "fetch_tavily", fake_fetch_tavily)

    multi_payload = {
        "id": "gen-multi",
        "model": "anthropic/claude-sonnet-4-6",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(
                        {
                            "is_hot_event": True,
                            "rejection_reason": None,
                            "facts": {
                                "entities": ["Donald Trump", "China"],
                                "what": "Donald Trump arrived in Beijing for a state visit.",
                                "when": "2026-05-14T08:00:00Z",
                                "where": "Beijing, China",
                                "why": None,
                                "supporting_sources": ["src_x1", "src_x2"],
                            },
                            "canonical_title": "Trump's 2026 state visit to China",
                            "confidence": 0.95,
                            "reasoning": "Two T0 sources confirm an unfolding diplomatic event.",
                        }
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 410, "completion_tokens": 92, "total_tokens": 502},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=multi_payload)
    )

    out = await ground.run("Trump visits China this week")
    assert out.is_hot_event is True
    assert out.facts is not None
    assert out.facts.entities == ["Donald Trump", "China"]
    assert out.facts.where == "Beijing, China"
