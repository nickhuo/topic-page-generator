"""Block-extract stage: one LLM call per section, returning RenderedSection."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from generator.blocks.schema import NewsCard
from generator.llm.trace_buffer import reset
from generator.pipeline.block_extract import (
    _canonicalize_news_cards,
    extract_one_section,
    run_block_extract_stage,
)
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    RenderedSection,
    SectionPlan,
    Source,
    SourceRights,
)

FIX = Path(__file__).parent.parent / "fixtures"


def _section(sid="overview", block="paragraph") -> SectionPlan:
    return SectionPlan(
        section_id=sid,
        kind="backbone",
        title=sid.title(),
        rank=1,
        block_kind=block,  # type: ignore[arg-type]
        intent="i",
        acceptance=AcceptanceCriteria(description="d"),
    )


def _source(sid: str = "s1") -> Source:
    return Source(
        id=sid,
        url="https://reuters.com/a",
        publisher=Publisher(name="Reuters", tier="T1"),
        title="t",
        published_at="2026-03-19T12:00:00Z",
        fetched_at="2026-03-19T13:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )


@respx.mock
async def test_extract_one_paragraph_section(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_block_paragraph_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    rs = await extract_one_section(
        section=_section(),
        sources=[_source()],
        canonical_title="t",
    )
    assert isinstance(rs, RenderedSection)
    assert rs.section_id == "overview"
    assert rs.block_kind == "paragraph"
    assert rs.block_data.kind == "paragraph"
    assert rs.eval_passed is True


@respx.mock
async def test_extract_one_timeline_section(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_block_timeline_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    rs = await extract_one_section(
        section=_section("timeline", "timeline"),
        sources=[_source()],
        canonical_title="t",
    )
    assert rs is not None
    assert rs.block_kind == "timeline"
    assert rs.block_data.kind == "timeline"


@respx.mock
async def test_extract_drops_section_when_minimum_viable_fails(monkeypatch):
    """If the block fails BlockSpec.is_minimum_viable, the section is dropped (None)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    # Empty-paragraph response — paragraph spec rejects all-whitespace.
    envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"kind":"paragraph","style":"prose","paragraphs_md":["   "],"pull_quotes":[],"citations":[]}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=envelope)
    )
    rs = await extract_one_section(
        section=_section(), sources=[_source()], canonical_title="t"
    )
    assert rs is None


@respx.mock
async def test_extract_drops_section_with_uncited_source_id(monkeypatch):
    """If the LLM cites s2 but s2 isn't in the evidence pool, drop the section."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": '{"kind":"paragraph","style":"prose","paragraphs_md":["Something real."],"pull_quotes":[],"citations":[{"source_id":"s_FAKE"}]}',
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=envelope)
    )
    rs = await extract_one_section(
        section=_section(), sources=[_source("s1")], canonical_title="t"
    )
    assert rs is None


async def test_run_block_extract_stage_parallel(monkeypatch):
    """run_block_extract_stage gathers all sections in parallel and drops None results."""

    async def fake_extract(
        *,
        section,
        sources,
        canonical_title,
        entities=None,
        model=None,
        reporter=None,
        editor_note=None,
    ):
        from generator.blocks.schema import ParagraphBlockData

        if section.section_id == "drop":
            return None
        return RenderedSection(
            section_id=section.section_id,
            block_kind="paragraph",
            block_data=ParagraphBlockData(paragraphs_md=["x"]),
        )

    monkeypatch.setattr(
        "generator.pipeline.block_extract.extract_one_section", fake_extract
    )
    out = await run_block_extract_stage(
        sections=[_section("a"), _section("drop"), _section("b")],
        evidence_by_section={"a": [_source()], "drop": [_source()], "b": [_source()]},
        canonical_title="t",
    )
    ids = [r.section_id for r in out]
    assert ids == ["a", "b"]


# ---------------------------------------------------------------------------
# Gallery-path tests
# ---------------------------------------------------------------------------


def _gallery_section(sid: str = "photos") -> SectionPlan:
    return SectionPlan(
        section_id=sid,
        kind="curated",
        title="Photos",
        rank=7,
        block_kind="gallery",
        intent="key visuals from the event",
        acceptance=AcceptanceCriteria(description="≥3 images"),
    )


@respx.mock
async def test_extract_gallery_section_calls_brave_and_llm(monkeypatch):
    """Gallery section: Brave is called, LLM picks images, RenderedSection is returned."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test")
    reset()

    async def fake_brave(query, *, count=10, timeout=12.0):
        from generator.sources.brave import BraveImageResult

        return [
            BraveImageResult(
                image_url=f"https://img.example/{i}.jpg",
                source_url=f"https://page.example/{i}",
                title=f"Image {i}",
                publisher="P",
            )
            for i in range(5)
        ]

    monkeypatch.setattr(
        "generator.pipeline.block_extract.fetch_brave_images", fake_brave
    )

    envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": (
                        '{"kind":"gallery","items":['
                        '{"image_url":"https://img.example/0.jpg","caption":"First","alt_text":"Alt 1","source_url":"https://page.example/0"},'
                        '{"image_url":"https://img.example/1.jpg","caption":"Second","alt_text":"Alt 2","source_url":"https://page.example/1"},'
                        '{"image_url":"https://img.example/2.jpg","caption":"Third","alt_text":"Alt 3","source_url":"https://page.example/2"}'
                        '],"citations":[]}'
                    ),
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=envelope)
    )

    rs = await extract_one_section(
        section=_gallery_section(),
        sources=[_source()],
        canonical_title="t",
    )
    assert rs is not None
    assert rs.block_kind == "gallery"
    assert len(rs.block_data.items) == 3


async def test_extract_gallery_drops_section_when_brave_misconfigured(monkeypatch):
    """No BRAVE_API_KEY: gallery sections are dropped (None returned), no crash."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    reset()

    async def raising_brave(query, *, count=10, timeout=12.0):
        from generator.sources.brave import BraveConfigError

        raise BraveConfigError("no key")

    monkeypatch.setattr(
        "generator.pipeline.block_extract.fetch_brave_images", raising_brave
    )

    rs = await extract_one_section(
        section=_gallery_section(),
        sources=[_source()],
        canonical_title="t",
    )
    assert rs is None


async def test_extract_gallery_drops_section_when_brave_returns_too_few(monkeypatch):
    """Brave returns 1 image: not enough headroom for LLM picking. Drop."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("BRAVE_API_KEY", "brave-test")
    reset()

    async def thin_brave(query, *, count=10, timeout=12.0):
        from generator.sources.brave import BraveImageResult

        return [BraveImageResult(image_url="https://img.example/0.jpg", title="x")]

    monkeypatch.setattr(
        "generator.pipeline.block_extract.fetch_brave_images", thin_brave
    )

    rs = await extract_one_section(
        section=_gallery_section(),
        sources=[_source()],
        canonical_title="t",
    )
    assert rs is None


# ---------------------------------------------------------------------------
# News-card URL canonicalization (repairs LLM-corrupted urls)
# ---------------------------------------------------------------------------


def _news_source(sid: str, url: str, pub: str = "Reuters", tier: str = "T1") -> Source:
    return Source(
        id=sid,
        url=url,
        publisher=Publisher(name=pub, tier=tier),
        title=f"title {sid}",
        published_at="2026-05-20T12:00:00Z",
        fetched_at="2026-05-20T13:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
        thumbnail_url=f"https://img.example/{sid}.jpg",
    )


def _news_card(url: str, **kw) -> NewsCard:
    base = dict(
        url=url,
        title="card",
        publisher="Wrong",
        tier="T3",
        published_at="2026-01-01T00:00:00Z",
        thumbnail_url="https://img.example/wrong.jpg",
    )
    base.update(kw)
    return NewsCard(**base)


def test_canonicalize_repairs_trailing_quote_comma():
    src = _news_source("s1", "https://reuters.com/a")
    # LLM appended "',", and a /published_at field-name leak on another card.
    cards = [
        _news_card("https://reuters.com/a',"),
        _news_card("https://reuters.com/a/published_at"),
    ]
    out = _canonicalize_news_cards(cards, [src])
    assert all(str(c.url) == "https://reuters.com/a" for c in out)
    assert all(c.source_id == "s1" for c in out)
    assert all(c.publisher == "Reuters" and c.tier == "T1" for c in out)


def test_canonicalize_prefers_longest_prefix():
    short = _news_source("short", "https://site.com/news")
    long = _news_source("long", "https://site.com/news/article-2026")
    # Corrupted URL belongs to the longer article; must not collapse to `short`.
    cards = [_news_card("https://site.com/news/article-2026','title':'x")]
    out = _canonicalize_news_cards(cards, [short, long])
    assert str(out[0].url) == "https://site.com/news/article-2026"
    assert out[0].source_id == "long"


def test_canonicalize_passes_through_unmatched_card():
    src = _news_source("s1", "https://reuters.com/a")
    card = _news_card("https://elsewhere.com/x")
    out = _canonicalize_news_cards([card], [src])
    assert out[0] is card  # unchanged identity — no match, no rewrite


def test_canonicalize_preserves_llm_summary():
    src = _news_source("s1", "https://reuters.com/a")
    card = _news_card("https://reuters.com/a',", summary="A neutral sentence.")
    out = _canonicalize_news_cards([card], [src])
    assert out[0].summary == "A neutral sentence."
    assert str(out[0].url) == "https://reuters.com/a"


@respx.mock
async def test_extract_latest_news_repairs_corrupted_urls(monkeypatch):
    """End-to-end: a latest_news section with a corrupted card url is repaired
    against the evidence pool before viability/render."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    sources = [
        _news_source("s1", "https://reuters.com/a", pub="Reuters"),
        _news_source("s2", "https://apnews.com/b", pub="AP"),
        _news_source("s3", "https://npr.org/c", pub="NPR"),
        _news_source("s4", "https://bbc.com/d", pub="BBC"),
    ]
    # First card url is corrupted with a trailing "',"; rest are clean.
    content = json.dumps(
        {
            "kind": "latest_news",
            "cards": [
                {
                    "url": "https://reuters.com/a',",
                    "title": "A",
                    "publisher": "Reuters",
                    "tier": "T1",
                    "published_at": "2026-05-20T12:00:00Z",
                    "thumbnail_url": "https://img.example/s1.jpg",
                    "source_id": "s1",
                },
                {
                    "url": "https://apnews.com/b",
                    "title": "B",
                    "publisher": "AP",
                    "tier": "T1",
                    "published_at": "2026-05-19T12:00:00Z",
                    "thumbnail_url": "https://img.example/s2.jpg",
                    "source_id": "s2",
                },
                {
                    "url": "https://npr.org/c",
                    "title": "C",
                    "publisher": "NPR",
                    "tier": "T1",
                    "published_at": "2026-05-18T12:00:00Z",
                    "thumbnail_url": "https://img.example/s3.jpg",
                    "source_id": "s3",
                },
                {
                    "url": "https://bbc.com/d",
                    "title": "D",
                    "publisher": "BBC",
                    "tier": "T1",
                    "published_at": "2026-05-17T12:00:00Z",
                    "thumbnail_url": "https://img.example/s4.jpg",
                    "source_id": "s4",
                },
            ],
        }
    )
    envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 120, "total_tokens": 320},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=envelope)
    )
    rs = await extract_one_section(
        section=_section("latest", "latest_news"),
        sources=sources,
        canonical_title="t",
    )
    assert rs is not None
    repaired = next(c for c in rs.block_data.cards if c.source_id == "s1")
    assert str(repaired.url) == "https://reuters.com/a"
    assert "'" not in str(repaired.url)
