import json
from pathlib import Path

import httpx
import respx

from generator.sources.wikipedia import fetch_wikipedia

FIXTURES = Path(__file__).parent / "fixtures"


@respx.mock
async def test_fetch_wikipedia_happy_path():
    payload = json.loads((FIXTURES / "wikipedia_gpt55_summary.json").read_text())
    respx.get(
        "https://en.wikipedia.org/api/rest_v1/page/summary/GPT-5.5"
    ).mock(return_value=httpx.Response(200, json=payload))
    source = await fetch_wikipedia("GPT-5.5")
    assert source is not None
    assert source.publisher.tier == "T2"
    assert source.publisher.name == "Wikipedia"
    assert str(source.url) == "https://en.wikipedia.org/wiki/GPT-5.5"
    assert source.language == "en"
    assert source.id.startswith("src_")


@respx.mock
async def test_fetch_wikipedia_not_found_returns_none():
    # Direct summary lookup 404s.
    respx.get(
        host="en.wikipedia.org", path__startswith="/api/rest_v1/page/summary"
    ).mock(return_value=httpx.Response(404, json={"type": "not_found"}))
    # Search fallback returns no hits.
    respx.get(host="en.wikipedia.org", path__startswith="/w/api.php").mock(
        return_value=httpx.Response(200, json={"query": {"search": []}})
    )
    source = await fetch_wikipedia("Nonexistent Entity 9z9z9")
    assert source is None
