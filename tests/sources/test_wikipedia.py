"""Tests for the Wikipedia REST summary fetcher."""

from __future__ import annotations

import httpx
import respx

from generator.sources.wikipedia import fetch_wikipedia_card


@respx.mock
async def test_fetch_wikipedia_card_returns_data():
    payload = {
        "title": "GPT-5.5",
        "extract": "GPT-5.5 is a large language model developed by OpenAI.",
        "thumbnail": {
            "source": "https://upload.wikimedia.org/wikipedia/commons/thumb/x/x.jpg"
        },
        "content_urls": {
            "desktop": {"page": "https://en.wikipedia.org/wiki/GPT-5.5"}
        },
    }
    respx.get(host="en.wikipedia.org", path__startswith="/api/rest_v1/page/summary/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    card = await fetch_wikipedia_card("GPT-5.5")
    assert card is not None
    assert card.title == "GPT-5.5"
    assert "GPT-5.5" in card.summary_text
    assert str(card.article_url) == "https://en.wikipedia.org/wiki/GPT-5.5"


@respx.mock
async def test_fetch_wikipedia_card_returns_none_on_404():
    respx.get(host="en.wikipedia.org", path__startswith="/api/rest_v1/page/summary/").mock(
        return_value=httpx.Response(404, json={"type": "not_found"})
    )
    card = await fetch_wikipedia_card("Nonexistent Title 9z9z9")
    assert card is None


@respx.mock
async def test_fetch_wikipedia_card_truncates_long_extract():
    long_extract = "A" * 2000
    payload = {
        "title": "Long Article",
        "extract": long_extract,
        "content_urls": {
            "desktop": {"page": "https://en.wikipedia.org/wiki/Long_Article"}
        },
    }
    respx.get(host="en.wikipedia.org", path__startswith="/api/rest_v1/page/summary/").mock(
        return_value=httpx.Response(200, json=payload)
    )
    card = await fetch_wikipedia_card("Long Article")
    assert card is not None
    assert len(card.summary_text) <= 600
