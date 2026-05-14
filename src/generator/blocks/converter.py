"""Adapt TypedModule data → RenderBlock data for templates.

This is the boundary between the content contract (what LLM extracted) and the
presentation contract (what templates consume). Each module kind maps to a
"natural" BlockKind, and a per-need `render_override` can pick a different
adaptation when more than one makes sense (e.g. schedule → timeline or map).
"""

from __future__ import annotations

from typing import Iterable

from generator.blocks.schema import (
    ChartBlockData,
    ChartStat,
    ComparisonRow,
    ComparisonTable,
    FactsheetBlockData,
    FactsheetRow,
    Location,
    MapBlockData,
    NewsCard,
    NewsfeedBlockData,
    ParagraphBlockData,
    PullQuote,
    RenderBlock,
    TimelineBlockData,
    TimelineEntry,
)
from generator.schema import (
    BlockKind,
    Citation,
    Source,
    TypedModule,
)


# Default BlockKind for each module kind — used when no render_override is set.
_DEFAULT_BLOCK_KIND: dict[str, BlockKind] = {
    "hero": "paragraph",  # hero is chrome, but if it ever flows into a section, paragraph form
    "infobox": "factsheet",
    "schedule": "timeline",
    "countdown": "timeline",  # also chrome usually; timeline is the fallback
    "kpi_numbers": "chart",
    "comparison": "chart",
    "changelog": "timeline",
    "reactions": "newsfeed",
    "media_coverage": "newsfeed",
    "official_statements": "newsfeed",
    "where_to_watch": "newsfeed",
    "background": "paragraph",
}


def default_block_kind(module_kind: str) -> BlockKind:
    return _DEFAULT_BLOCK_KIND.get(module_kind, "paragraph")


def module_to_block(
    module: TypedModule,
    sources: list[Source],
    override: BlockKind | None = None,
) -> RenderBlock:
    """Dispatch a TypedModule to its RenderBlock adaptation.

    `sources` is the full page evidence pool — used to resolve source_id → URL
    when building newsfeed cards. `override` (from need plan) wins over the
    module's natural block kind when present and supported.
    """
    src_by_id = {s.id: s for s in sources}
    kind = override or default_block_kind(module.kind)
    citations: list[Citation] = list(module.citations or [])

    if kind == "paragraph":
        return _to_paragraph(module, citations)
    if kind == "factsheet":
        return _to_factsheet(module)
    if kind == "timeline":
        return _to_timeline(module)
    if kind == "chart":
        return _to_chart(module)
    if kind == "newsfeed":
        return _to_newsfeed(module, src_by_id)
    if kind == "map":
        return _to_map(module)
    return _to_paragraph(module, citations)  # safe fallback


# ---------------------------------------------------------------------------
# Per-block adapters
# ---------------------------------------------------------------------------
def _to_paragraph(module: TypedModule, citations: list[Citation]) -> ParagraphBlockData:
    paragraphs: list[str] = []
    pull_quotes: list[PullQuote] = []
    cite_acc = list(citations)

    if module.kind == "background":
        for p in module.data.paragraphs:
            paragraphs.append(p.text)
            cite_acc.extend(p.citations or [])
    elif module.kind == "hero":
        paragraphs.append(module.data.summary or module.data.title)
    elif module.kind == "official_statements":
        # Render each statement as a paragraph + a pull quote.
        for item in module.data.items:
            paragraphs.append(
                f"**{item.author}**, {item.role}, {item.organization}: "
                f"“{item.quote}”"
            )
            pull_quotes.append(
                PullQuote(
                    quote=item.quote,
                    attribution=f"{item.author}, {item.role}",
                    source_id=item.source_id,
                )
            )
    else:
        paragraphs.append(str(module.data))

    if not paragraphs:
        paragraphs = ["(no content)"]
    return ParagraphBlockData(
        paragraphs_md=paragraphs,
        pull_quotes=pull_quotes,
        citations=cite_acc,
    )


def _to_factsheet(module: TypedModule) -> FactsheetBlockData:
    if module.kind == "infobox":
        rows = [
            FactsheetRow(label=r.label, value=r.value, source_id=r.source_id)
            for r in module.data.rows
        ]
    else:
        rows = [FactsheetRow(label=module.kind, value=str(module.data))]
    if not rows:
        rows = [FactsheetRow(label="(empty)", value="—")]
    return FactsheetBlockData(rows=rows)


def _to_timeline(module: TypedModule) -> TimelineBlockData:
    entries: list[TimelineEntry] = []
    timezone = None
    if module.kind == "schedule":
        timezone = module.data.timezone
        for item in module.data.items:
            entries.append(
                TimelineEntry(
                    title=item.label,
                    time=item.time_iso,
                    location=item.location,
                    source_id=item.source_id,
                )
            )
    elif module.kind == "changelog":
        for e in module.data.entries:
            entries.append(
                TimelineEntry(
                    title=e.label,
                    description=e.description,
                    importance=e.importance,
                    source_id=e.source_id,
                )
            )
    elif module.kind == "countdown":
        entries.append(
            TimelineEntry(
                title=module.data.label,
                time=module.data.target_at,
                source_id=module.data.source_id,
            )
        )
    if not entries:
        entries = [TimelineEntry(title="(no entries)")]
    return TimelineBlockData(entries=entries, timezone=timezone)


def _to_chart(module: TypedModule) -> ChartBlockData:
    if module.kind == "kpi_numbers":
        stats = [
            ChartStat(
                value=t.value,
                unit=t.unit,
                label=t.label,
                comparison=t.comparison,
                source_id=t.source_id,
            )
            for t in module.data.tiles
        ]
        return ChartBlockData(chart_type="stat", stats=stats)
    if module.kind == "comparison":
        subjects = [s.name for s in module.data.subjects]
        rows = [
            ComparisonRow(axis=a.label, cells=[c.value for c in a.cells])
            for a in module.data.axes
        ]
        return ChartBlockData(
            chart_type="compare_table",
            table=ComparisonTable(subjects=subjects, rows=rows),
        )
    # Fallback bar from a single value
    return ChartBlockData(
        chart_type="stat",
        stats=[ChartStat(value="—", label=module.kind)],
    )


def _to_newsfeed(
    module: TypedModule, src_by_id: dict[str, Source]
) -> NewsfeedBlockData:
    cards: list[NewsCard] = []
    variant: str = "news"
    if module.kind == "media_coverage":
        for it in module.data.items:
            cards.append(
                NewsCard(
                    url=it.url,
                    title=it.headline,
                    publisher=it.publisher,
                    tier=it.publisher_tier,
                    published_at=it.published_at,
                    summary=it.snippet,
                    source_id=it.source_id,
                    thumbnail_url=_thumb_for_source_id(it.source_id, src_by_id),
                )
            )
        grouping = module.data.grouping_strategy
    elif module.kind == "reactions":
        variant = "quotes"
        grouping = "flat"
        for it in module.data.items:
            src = src_by_id.get(it.source_id)
            cards.append(
                NewsCard(
                    url=src.url if src else "https://example.invalid/",  # type: ignore[arg-type]
                    title=f"{it.author} — {it.author_role}",
                    publisher=src.publisher.name if src else "Unknown",
                    tier=src.publisher.tier if src else "T3",
                    published_at=src.published_at if src else None,
                    summary=it.quote,
                    source_id=it.source_id,
                    thumbnail_url=src.thumbnail_url if src else None,
                )
            )
    elif module.kind == "official_statements":
        variant = "quotes"
        grouping = "flat"
        for it in module.data.items:
            cards.append(
                NewsCard(
                    url=it.source_url,
                    title=f"{it.author}, {it.role} ({it.organization})",
                    publisher=it.organization,
                    tier="T0",
                    published_at=it.made_at,
                    summary=it.quote,
                    source_id=it.source_id,
                )
            )
    elif module.kind == "where_to_watch":
        variant = "channels"
        grouping = "flat"
        for c in module.data.channels:
            cards.append(
                NewsCard(
                    url=c.url or "https://example.invalid/",  # type: ignore[arg-type]
                    title=f"{c.type.upper()} — {c.name}",
                    publisher=c.name,
                    tier="T0",
                    published_at=None,
                    summary=" / ".join(filter(None, [c.region, c.cost])),
                    source_id=c.source_id,
                )
            )
    else:
        grouping = "flat"

    if not cards:
        # Discriminated-union schema requires min_length=1; fall back to a placeholder.
        cards = [
            NewsCard(
                url="https://example.invalid/",  # type: ignore[arg-type]
                title="(no items)",
                publisher="—",
                tier="T3",
            )
        ]
    return NewsfeedBlockData(cards=cards, variant=variant, grouping=grouping)


def _to_map(module: TypedModule) -> MapBlockData:
    if module.kind == "schedule":
        locs: Iterable[Location] = (
            Location(name=item.location or item.label)
            for item in module.data.items
            if item.location
        )
        out = list(locs)
        if not out:
            out = [Location(name=item.label) for item in module.data.items]
        return MapBlockData(locations=out or [Location(name="(no locations)")])
    return MapBlockData(locations=[Location(name=module.kind)])


def _thumb_for_source_id(
    source_id: str, src_by_id: dict[str, Source]
):
    s = src_by_id.get(source_id)
    return s.thumbnail_url if s else None
