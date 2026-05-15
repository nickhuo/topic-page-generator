"""Tests for OG image extraction + enrichment."""

from __future__ import annotations

import httpx
import respx

from generator.schema import Publisher, Source, SourceRights
from generator.sources.og_image import enrich_thumbnails, extract_og_image


def _src(url: str, *, thumb: str | None = None) -> Source:
    return Source(
        id="s_" + url.rsplit("/", 1)[-1],
        url=url,
        publisher=Publisher(name="P", tier="T0"),
        title="t",
        published_at="2026-05-01T00:00:00Z",
        fetched_at="2026-05-01T00:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=10000, can_paraphrase=True),
        thumbnail_url=thumb,  # type: ignore[arg-type]
    )


def test_extract_og_image_property_first():
    html = (
        "<html><head>"
        '<meta property="og:image" content="https://cdn.example/a.jpg">'
        "</head></html>"
    )
    assert (
        extract_og_image(html, "https://example.com/article")
        == "https://cdn.example/a.jpg"
    )


def test_extract_og_image_content_first():
    html = (
        "<html><head>"
        '<meta content="https://cdn.example/b.jpg" property="og:image">'
        "</head></html>"
    )
    assert extract_og_image(html, "https://example.com/") == "https://cdn.example/b.jpg"


def test_extract_og_image_secure_url_variant():
    html = (
        "<html><head>"
        '<meta property="og:image:secure_url" content="https://cdn.example/s.jpg">'
        "</head></html>"
    )
    assert extract_og_image(html, "https://example.com/") == "https://cdn.example/s.jpg"


def test_extract_og_image_relative_url_resolved():
    html = '<meta property="og:image" content="/img/x.jpg">'
    got = extract_og_image(html, "https://example.com/news/article")
    assert got == "https://example.com/img/x.jpg"


def test_extract_og_image_twitter_fallback():
    html = '<meta name="twitter:image" content="https://cdn.example/t.jpg">'
    assert extract_og_image(html, "https://example.com/") == "https://cdn.example/t.jpg"


def test_extract_og_image_none_when_absent():
    assert (
        extract_og_image("<html><head></head></html>", "https://example.com/") is None
    )


@respx.mock
async def test_enrich_thumbnails_fills_only_missing():
    respx.get("https://news.example/a").mock(
        return_value=httpx.Response(
            200,
            text='<meta property="og:image" content="https://cdn.example/a.jpg">',
        )
    )
    # Source with an existing thumbnail must not be re-fetched.
    respx.get("https://news.example/b").mock(
        return_value=httpx.Response(500, text="boom")
    )
    sources = [
        _src("https://news.example/a"),
        _src("https://news.example/b", thumb="https://existing.example/b.jpg"),
    ]
    await enrich_thumbnails(sources)
    assert str(sources[0].thumbnail_url).startswith("https://cdn.example/a.jpg")
    assert str(sources[1].thumbnail_url) == "https://existing.example/b.jpg"


@respx.mock
async def test_enrich_thumbnails_swallows_errors():
    respx.get("https://news.example/x").mock(side_effect=httpx.ConnectError("boom"))
    src = _src("https://news.example/x")
    await enrich_thumbnails([src])
    # No raise; source stays image-less and will be filtered downstream.
    assert src.thumbnail_url is None
