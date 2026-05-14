import json
from pathlib import Path

import httpx
import respx

from generator.sources.tavily import fetch_tavily

FIXTURES = Path(__file__).parent / "fixtures"


@respx.mock
async def test_fetch_tavily_happy_path(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    payload = json.loads((FIXTURES / "tavily_results.json").read_text())
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json=payload)
    )

    sources = await fetch_tavily(
        "GPT-5.5 Instant ChatGPT",
        time_range_days=14,
        max_results=5,
        primary_entity="OpenAI GPT-5.5",
    )
    assert len(sources) == 2
    reuters = next(s for s in sources if "reuters.com" in str(s.url))
    openai_src = next(s for s in sources if str(s.url).startswith("https://openai.com"))
    assert reuters.publisher.tier == "T1"
    assert openai_src.publisher.tier == "T0"


@respx.mock
async def test_fetch_tavily_retry_on_429(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    payload = json.loads((FIXTURES / "tavily_results.json").read_text())
    route = respx.post("https://api.tavily.com/search").mock(
        side_effect=[
            httpx.Response(429),
            httpx.Response(429),
            httpx.Response(200, json=payload),
        ]
    )
    sources = await fetch_tavily("q", time_range_days=14, max_results=5)
    assert len(sources) == 2
    assert route.call_count == 3


@respx.mock
async def test_fetch_tavily_zero_results(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    sources = await fetch_tavily("q", time_range_days=14, max_results=5)
    assert sources == []
