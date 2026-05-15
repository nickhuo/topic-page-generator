"""Stage 4 — Fetch. Needs-driven multi-query fan-out with publisher diversity.

Each activated need in the plan brings 1-2 Tavily queries; we fan all of them
out in parallel (semaphore-bounded), tag returned Sources with the need they
serve, merge across queries with URL dedup that preserves serves_needs, and
optionally enrich each source's thumbnail + summary via OpenGraph scraping.
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime

from generator.schema import (
    EventSubject,
    NeedId,
    NeedPlanOutput,
    Source,
)
from generator.sources._common import host_of
from generator.sources.og_scrape import enrich_sources
from generator.sources.tavily import fetch_tavily
from generator.sources.wikidata import fetch_wikidata

log = logging.getLogger(__name__)


class EmptyEvidencePoolError(RuntimeError):
    """Raised when all source clients return zero results."""


AI_CONTENT_BLACKLIST: frozenset[str] = frozenset(
    {
        "aigeneratednews.example",
        "ai-content.example",
        "auto-news.example",
        "newsbot.example",
        "copydesk.ai",
        "syntheticnews.example",
        "robonews.example",
        "aifeed.example",
        "neuralwire.example",
        "writebot.example",
    }
)

_TIER_ORDER = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}
_FETCH_CONCURRENCY = 6


def _is_blacklisted(url: str) -> bool:
    h = host_of(url)
    return any(bad in h for bad in AI_CONTENT_BLACKLIST)


def _iso_to_epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


def _dedupe_preserving_needs(sources: list[Source]) -> list[Source]:
    """Dedupe by URL, but merge `serves_needs` across duplicates so a single
    source surfaced by two different need queries records both."""
    seen: dict[str, Source] = {}
    for s in sources:
        key = str(s.url)
        existing = seen.get(key)
        if existing is None:
            seen[key] = s
            continue
        merged_needs = list(dict.fromkeys([*existing.serves_needs, *s.serves_needs]))
        seen[key] = existing.model_copy(update={"serves_needs": merged_needs})
    return list(seen.values())


async def _fetch_one_query(
    sem: asyncio.Semaphore,
    need_id: NeedId,
    query: str,
    time_range_days: int,
    primary_entity: str,
) -> list[Source]:
    async with sem:
        results = await fetch_tavily(
            query,
            time_range_days=time_range_days,
            max_results=8,
            primary_entity=primary_entity,
        )
    return [s.model_copy(update={"serves_needs": [need_id]}) for s in results]


async def run_fetch_stage(
    need_plan: NeedPlanOutput, subject: EventSubject
) -> list[Source]:
    """Fan out one Tavily call per (need, fetch_query), gather Wikidata once,
    dedupe URLs while preserving need attribution, blacklist AI-content
    domains, enrich thumbnails+summaries via OG scrape, then sort by
    (tier asc, published_at desc)."""
    entity = subject.primary_entity
    sem = asyncio.Semaphore(_FETCH_CONCURRENCY)

    # Collect (need_id, query, days) triples from activated plans.
    fetch_specs: list[tuple[NeedId, str, int]] = []
    for plan in need_plan.need_plans:
        if not plan.activated:
            continue
        for fq in plan.fetch_queries:
            days = fq.time_range_days or 14
            fetch_specs.append((plan.need_id, fq.query, days))

    # Fallback: if no fetch queries at all (unusual), at least search the entity.
    if not fetch_specs:
        log.warning(
            "Plan emitted zero fetch_queries; falling back to single entity query."
        )
        fetch_specs = [("what_happened", entity, 14)]

    max_calls = int(os.getenv("MAX_TAVILY_CALLS", "20"))
    if len(fetch_specs) > max_calls:
        log.warning(
            "Plan asked for %d Tavily calls; clamping to MAX_TAVILY_CALLS=%d.",
            len(fetch_specs),
            max_calls,
        )
        fetch_specs = fetch_specs[:max_calls]

    wikidata_task = fetch_wikidata(entity)
    tavily_tasks = [
        _fetch_one_query(sem, need_id, query, days, entity)
        for (need_id, query, days) in fetch_specs
    ]
    wd_res, *tav_results = await asyncio.gather(wikidata_task, *tavily_tasks)

    merged: list[Source] = []
    wd_source, _wd_props = wd_res
    if wd_source is not None:
        # Wikidata serves "who_involved" / "what_happened" by default.
        merged.append(
            wd_source.model_copy(
                update={"serves_needs": ["who_involved", "what_happened"]}
            )
        )
    for batch in tav_results:
        merged.extend(batch)

    merged = [s for s in merged if not _is_blacklisted(str(s.url))]
    merged = _dedupe_preserving_needs(merged)

    if not merged:
        raise EmptyEvidencePoolError(
            f"No sources found for entity={entity!r}. Tried Wikidata and Tavily."
        )

    merged = await enrich_sources(merged)

    merged.sort(
        key=lambda s: (
            _TIER_ORDER.get(s.publisher.tier, 9),
            -_iso_to_epoch(s.published_at),
        )
    )
    return merged
