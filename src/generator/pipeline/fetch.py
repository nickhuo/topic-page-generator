"""Stage 4 — Fetch orchestrator. Fires two clients in parallel, dedupes,
filters AI-content blacklist, sorts by (tier asc, published_at desc)."""

from __future__ import annotations

import asyncio
from datetime import datetime

from generator.schema import EventSubject, PlanOutput, Source
from generator.sources._common import host_of
from generator.sources.tavily import fetch_tavily
from generator.sources.wikidata import fetch_wikidata


class EmptyEvidencePoolError(RuntimeError):
    """Raised when all source clients return zero results."""


# TODO(pr-future): replace placeholders with a curated AI-content domain list.
# Reuters investigation (2024) listed 40+ AI-aggregator domains; mirror a
# small placeholder subset until the real list is integrated.
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


def _is_blacklisted(url: str) -> bool:
    h = host_of(url)
    return any(bad in h for bad in AI_CONTENT_BLACKLIST)


def _dedupe_by_url(sources: list[Source]) -> list[Source]:
    seen: set[str] = set()
    out: list[Source] = []
    for s in sources:
        key = str(s.url)
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _iso_to_epoch(iso: str) -> float:
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


async def run_fetch_stage(plan: PlanOutput, subject: EventSubject) -> list[Source]:
    """Fan out to Wikidata + Tavily, then merge → dedupe → blacklist → sort.

    Wikipedia was removed: its summary endpoint adds latency without offering
    anything Wikidata + Tavily don't already cover for the event types we ship
    (product launches, scheduled events, live cultural events). Any wikipedia.org
    URLs that come through Tavily still get T2 via `publisher_tier.PUBLISHER_TIERS`.
    """
    entity = subject.primary_entity
    days = plan.source_strategy.time_range_days
    query = entity
    if subject.event_type_hint:
        query = f"{entity} {subject.event_type_hint.replace('_', ' ')}"

    # TODO(pr-3+): when an event subject is a product (e.g. "GPT-5.5 Instant"),
    # the parent org ("OpenAI") may not appear in primary_entity, which means
    # tier_for() will miss T0 attribution for openai.com. Pass richer context
    # here — input_sentence and any disambiguation-derived org names — once
    # those flow through. For now the triage stub returns "X (Org)" so the
    # substring rule resolves correctly.
    wikidata_task = fetch_wikidata(entity)
    tavily_task = fetch_tavily(
        query, time_range_days=days, max_results=10, primary_entity=entity
    )

    wd_res, tav_res = await asyncio.gather(wikidata_task, tavily_task)

    merged: list[Source] = []
    wd_source, _wd_props = wd_res
    if wd_source is not None:
        merged.append(wd_source)
    merged.extend(tav_res)

    merged = [s for s in merged if not _is_blacklisted(str(s.url))]
    merged = _dedupe_by_url(merged)

    if not merged:
        raise EmptyEvidencePoolError(
            f"No sources found for entity={entity!r}. Tried Wikidata and Tavily."
        )

    merged.sort(
        key=lambda s: (
            _TIER_ORDER.get(s.publisher.tier, 9),
            -_iso_to_epoch(s.published_at),
        )
    )
    return merged
