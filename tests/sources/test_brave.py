"""Tests for the Brave Image Search client."""

from __future__ import annotations

import pytest
import httpx
import respx

from generator.sources.brave import (
    BraveConfigError,
    BraveImageResult,
    fetch_brave_images,
)

_ENDPOINT = "https://api.search.brave.com/res/v1/images/search"

_THREE_RESULTS = {
    "results": [
        {
            "url": "https://example.com/article-1",
            "title": "Image One Title",
            "source": "Example Publisher",
            "image": {"url": "https://example.com/img1.jpg", "width": 1280, "height": 720},
            "properties": {"url": "https://example.com/orig1.jpg"},
            "thumbnail": {"src": "https://example.com/thumb1.jpg"},
        },
        {
            "url": "https://news.example.org/story-2",
            "title": "Image Two Title",
            "source": "News Org",
            "image": {"url": "https://news.example.org/img2.jpg", "width": 800, "height": 600},
            "properties": {"url": "https://news.example.org/orig2.jpg"},
            "thumbnail": {"src": "https://news.example.org/thumb2.jpg"},
        },
        {
            "url": "https://media.site.com/photo-3",
            "title": "Image Three Title",
            "source": "Media Site",
            "image": {"url": "https://media.site.com/img3.jpg", "width": 640, "height": 480},
            "properties": {"url": "https://media.site.com/orig3.jpg"},
            "thumbnail": {"src": "https://media.site.com/thumb3.jpg"},
        },
    ]
}


@respx.mock
async def test_fetch_brave_images_happy(monkeypatch):
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test-key")
    route = respx.get(_ENDPOINT).mock(
        return_value=httpx.Response(200, json=_THREE_RESULTS)
    )

    results = await fetch_brave_images("test query", count=3)

    assert len(results) == 3
    assert all(isinstance(r, BraveImageResult) for r in results)

    # First result: properties.url takes priority over image.url
    assert str(results[0].image_url) == "https://example.com/orig1.jpg"
    assert str(results[0].source_url) == "https://example.com/article-1"
    assert results[0].title == "Image One Title"
    assert results[0].publisher == "Example Publisher"

    # Verify headers: X-Subscription-Token used, Authorization NOT used
    sent_headers = route.calls.last.request.headers
    assert sent_headers.get("x-subscription-token") == "brave-test-key"
    assert "authorization" not in sent_headers


@respx.mock
async def test_fetch_brave_images_missing_key_raises(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    with pytest.raises(BraveConfigError):
        await fetch_brave_images("test query")


@respx.mock
async def test_fetch_brave_images_count_clamped():
    """Count=1 is sent as-is; count=500 is clamped to 200."""
    route_capture = []

    async def _capture(request):
        route_capture.append(str(request.url))
        return httpx.Response(200, json={"results": []})

    import os
    os.environ["BRAVE_API_KEY"] = "key-for-clamp-test"

    respx.get(_ENDPOINT).mock(side_effect=_capture)

    await fetch_brave_images("q", count=1)
    assert "count=1" in route_capture[-1]

    await fetch_brave_images("q", count=500)
    assert "count=200" in route_capture[-1]

    del os.environ["BRAVE_API_KEY"]


@respx.mock
async def test_fetch_brave_images_handles_missing_optional_fields(monkeypatch):
    """Items missing `properties` or `image.url` should not crash."""
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test-key")

    payload = {
        "results": [
            # Has image.url but no properties
            {
                "url": "https://example.com/a1",
                "title": "A1",
                "source": "Pub",
                "image": {"url": "https://example.com/a1.jpg", "width": 100, "height": 100},
            },
            # Has only thumbnail (no image, no properties)
            {
                "url": "https://example.com/a2",
                "title": "A2",
                "source": "Pub2",
                "thumbnail": {"src": "https://example.com/thumb2.jpg"},
            },
            # Has nothing useful — should be dropped
            {
                "url": "https://example.com/a3",
                "title": "A3",
                "source": "Pub3",
            },
        ]
    }
    respx.get(_ENDPOINT).mock(return_value=httpx.Response(200, json=payload))

    results = await fetch_brave_images("query")
    # First two should succeed via fallback chain; third should be dropped
    assert len(results) == 2
    assert str(results[0].image_url) == "https://example.com/a1.jpg"
    assert str(results[1].image_url) == "https://example.com/thumb2.jpg"
