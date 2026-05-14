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
    route = respx.post("https://api.tavily.com/search").mock(
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
    sent_request = route.calls.last.request
    assert sent_request.headers.get("authorization") == "Bearer test-key"
    sent_body = json.loads(sent_request.content)
    assert "api_key" not in sent_body


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


@respx.mock
async def test_fetch_tavily_no_api_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    route = respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    sources = await fetch_tavily("q", time_range_days=14, max_results=5)
    assert sources == []
    assert route.call_count == 0


@respx.mock
async def test_fetch_tavily_non_200_status(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(400, json={"error": "bad query"})
    )
    sources = await fetch_tavily("q", time_range_days=14, max_results=5)
    assert sources == []


@respx.mock
async def test_fetch_tavily_skips_result_without_url(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    payload = {
        "results": [
            {"title": "no url here", "content": "x", "published_date": "2026-05-01"},
            {
                "title": "has url",
                "url": "https://openai.com/blog/x",
                "content": "y",
                "published_date": "2026-05-02",
            },
        ]
    }
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    sources = await fetch_tavily("q", time_range_days=14, max_results=5)
    assert len(sources) == 1
    assert str(sources[0].url).startswith("https://openai.com")


@respx.mock
async def test_fetch_tavily_preserves_iso_published_date(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")
    payload = {
        "results": [
            {
                "title": "t",
                "url": "https://openai.com/blog/x",
                "content": "c",
                "published_date": "2026-05-01T12:34:56Z",
            }
        ]
    }
    respx.post("https://api.tavily.com/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    sources = await fetch_tavily("q", time_range_days=14, max_results=5)
    assert len(sources) == 1
    assert sources[0].published_at == "2026-05-01T12:34:56Z"
