import pytest

from generator.pipeline.fetch import EmptyEvidencePoolError, run_fetch_stage
from generator.schema import (
    EventSubject,
    PlanComposition,
    PlanOutput,
    Publisher,
    Source,
    SourceRights,
    SourceStrategy,
)


def _mk_source(url: str, tier: str, published_at: str) -> Source:
    return Source(
        id=url,  # use URL as id for test determinism (Source.id is a str alias)
        url=url,
        publisher=Publisher(name="x", tier=tier),
        title="t",
        published_at=published_at,
        fetched_at="2026-05-13T12:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=False),
    )


PLAN = PlanOutput(
    archetype_hint="product_launch",
    layout_preset_id="product_focus",
    composition=[
        PlanComposition(
            module_kind="hero",
            artifact="HeroBanner",
            slot="hero",
            priority="required",
        )
    ],
    source_strategy=SourceStrategy(
        preferred_tiers=["T0", "T1", "T2"], time_range_days=14, min_publishers=2
    ),
)
SUBJECT = EventSubject(
    primary_entity="OpenAI", event_type_hint="product_launch", temporal_posture="recent"
)


async def test_run_fetch_dedup_blacklist_sort(monkeypatch):
    t0 = _mk_source("https://openai.com/blog/a", "T0", "2026-05-02T00:00:00Z")
    t1_new = _mk_source("https://reuters.com/y", "T1", "2026-05-05T00:00:00Z")
    t1_old = _mk_source("https://reuters.com/x", "T1", "2026-04-01T00:00:00Z")
    t2 = _mk_source("https://en.wikipedia.org/wiki/GPT", "T2", "2026-05-01T00:00:00Z")
    dup = _mk_source("https://reuters.com/y", "T1", "2026-05-05T00:00:00Z")
    blacklisted = _mk_source(
        "https://aigeneratednews.example/x", "T3", "2026-05-06T00:00:00Z"
    )

    async def fake_wd(*a, **kw):
        return (t2, {})

    async def fake_tav(*a, **kw):
        return [t0, t1_new, t1_old, dup, blacklisted]

    monkeypatch.setattr("generator.pipeline.fetch.fetch_wikidata", fake_wd)
    monkeypatch.setattr("generator.pipeline.fetch.fetch_tavily", fake_tav)
    monkeypatch.setattr(
        "generator.pipeline.fetch.AI_CONTENT_BLACKLIST",
        frozenset({"aigeneratednews.example"}),
    )

    out = await run_fetch_stage(PLAN, SUBJECT)
    urls = [str(s.url) for s in out]
    assert not any("aigeneratednews" in u for u in urls)
    assert urls.count("https://reuters.com/y") == 1
    tiers = [s.publisher.tier for s in out]
    assert tiers == sorted(tiers, key=lambda t: ["T0", "T1", "T2", "T3"].index(t))
    t1s = [s for s in out if s.publisher.tier == "T1"]
    assert t1s[0].published_at >= t1s[1].published_at


async def test_run_fetch_empty_raises(monkeypatch):
    async def empty_wd(*a, **kw):
        return (None, {})

    async def empty_t(*a, **kw):
        return []

    monkeypatch.setattr("generator.pipeline.fetch.fetch_wikidata", empty_wd)
    monkeypatch.setattr("generator.pipeline.fetch.fetch_tavily", empty_t)
    with pytest.raises(EmptyEvidencePoolError):
        await run_fetch_stage(PLAN, SUBJECT)
