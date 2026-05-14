import pytest

from generator.pipeline.fetch import EmptyEvidencePoolError, run_fetch_stage
from generator.schema import (
    EventSubject,
    FetchQuery,
    NeedCurationPlan,
    NeedPlanOutput,
    Publisher,
    Source,
    SourceRights,
    TierQuota,
)


def _mk_source(url: str, tier: str, published_at: str) -> Source:
    return Source(
        id=url,
        url=url,
        publisher=Publisher(name="x", tier=tier),
        title="t",
        published_at=published_at,
        fetched_at="2026-05-13T12:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=False),
    )


def _mk_plan(*need_ids: str) -> NeedPlanOutput:
    plans = []
    for i, nid in enumerate(need_ids, start=1):
        plans.append(
            NeedCurationPlan(
                need_id=nid,
                activated=True,
                rank=i,
                section_title=f"Title for {nid}",
                rationale="test",
                fetch_queries=[FetchQuery(query=f"q-{nid}", time_range_days=14)],
                assigned_modules=["hero"],
                publisher_quota=TierQuota(),
            )
        )
    # Pad with deactivated needs to fill all 8 (ranks 1..8 unique).
    fill = [
        "what_happened",
        "when_where",
        "who_involved",
        "current_state",
        "why_matters",
        "world_reaction",
        "what_can_do",
        "what_next",
    ]
    seen = set(need_ids)
    rank_iter = len(need_ids) + 1
    for nid in fill:
        if nid in seen:
            continue
        plans.append(
            NeedCurationPlan(
                need_id=nid,
                activated=False,
                rank=rank_iter,
                section_title="off",
                rationale="not relevant",
                fetch_queries=[],
                assigned_modules=[],
                publisher_quota=TierQuota(),
            )
        )
        rank_iter += 1
    return NeedPlanOutput(need_plans=plans, layout_preset_id="product_focus")


PLAN = _mk_plan("what_happened", "world_reaction")
SUBJECT = EventSubject(
    primary_entity="OpenAI", event_type_hint="product_launch", temporal_posture="recent"
)


async def test_run_fetch_dedup_blacklist_sort(monkeypatch):
    t0 = _mk_source("https://openai.com/blog/a", "T0", "2026-05-02T00:00:00Z")
    t1_new = _mk_source("https://reuters.com/y", "T1", "2026-05-05T00:00:00Z")
    t1_old = _mk_source("https://reuters.com/x", "T1", "2026-04-01T00:00:00Z")
    t2 = _mk_source("https://en.wikipedia.org/wiki/GPT", "T2", "2026-05-01T00:00:00Z")
    blacklisted = _mk_source(
        "https://aigeneratednews.example/x", "T3", "2026-05-06T00:00:00Z"
    )

    async def fake_wd(*a, **kw):
        return (t2, {})

    async def fake_tav(query, **kw):
        # Each query returns the same pool; dedup should collapse duplicates.
        return [t0, t1_new, t1_old, blacklisted]

    async def fake_enrich(sources):
        return sources  # OG scraping disabled in this unit test

    monkeypatch.setattr("generator.pipeline.fetch.fetch_wikidata", fake_wd)
    monkeypatch.setattr("generator.pipeline.fetch.fetch_tavily", fake_tav)
    monkeypatch.setattr("generator.pipeline.fetch.enrich_sources", fake_enrich)
    monkeypatch.setattr(
        "generator.pipeline.fetch.AI_CONTENT_BLACKLIST",
        frozenset({"aigeneratednews.example"}),
    )

    out = await run_fetch_stage(PLAN, SUBJECT)
    urls = [str(s.url) for s in out]
    assert not any("aigeneratednews" in u for u in urls)
    # Two activated needs each fetched the same t1_new; dedup should leave one.
    assert urls.count("https://reuters.com/y") == 1
    tiers = [s.publisher.tier for s in out]
    assert tiers == sorted(tiers, key=lambda t: ["T0", "T1", "T2", "T3"].index(t))
    t1s = [s for s in out if s.publisher.tier == "T1"]
    assert t1s[0].published_at >= t1s[1].published_at
    # Deduped record should carry both serves_needs from the two queries that hit it.
    reuters_y = next(s for s in out if str(s.url) == "https://reuters.com/y")
    assert set(reuters_y.serves_needs) == {"what_happened", "world_reaction"}


async def test_run_fetch_empty_raises(monkeypatch):
    async def empty_wd(*a, **kw):
        return (None, {})

    async def empty_t(*a, **kw):
        return []

    async def fake_enrich(sources):
        return sources

    monkeypatch.setattr("generator.pipeline.fetch.fetch_wikidata", empty_wd)
    monkeypatch.setattr("generator.pipeline.fetch.fetch_tavily", empty_t)
    monkeypatch.setattr("generator.pipeline.fetch.enrich_sources", fake_enrich)
    with pytest.raises(EmptyEvidencePoolError):
        await run_fetch_stage(PLAN, SUBJECT)
