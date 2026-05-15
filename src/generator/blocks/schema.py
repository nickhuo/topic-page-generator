"""Render-block schemas — discriminated by `kind`.

Six block kinds map 1:1 to templates under `templates/blocks/`:
  paragraph / timeline / chart / newsfeed / factsheet / map

Module subclasses produce one of these via `to_block()`. Templates consume
only blocks, never raw module data.
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from generator.schema import (
    Citation,
    ISO8601,
    Sentiment,
    SourceId,
    SourceTier,
)


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# Shared block primitives
# ---------------------------------------------------------------------------
class PullQuote(_Frozen):
    quote: str
    attribution: str | None = None
    source_id: SourceId | None = None


class NewsCard(_Frozen):
    """A single card in a newsfeed block — link with thumbnail + summary."""

    url: HttpUrl
    title: str
    publisher: str
    tier: SourceTier
    published_at: ISO8601 | None = None
    thumbnail_url: HttpUrl | None = None
    summary: str | None = None
    source_id: SourceId | None = None


class TimelineEntry(_Frozen):
    title: str
    time: str | None = None  # free-form: ISO8601 / "Jun 11" / "Quarter Finals"
    location: str | None = None
    description: str | None = None
    importance: Literal["breaking", "feature", "minor", "normal"] = "normal"
    temporal_phase: Literal["past", "present", "future"] = "past"
    source_id: SourceId | None = None


class Location(_Frozen):
    name: str
    lat: float | None = None
    lon: float | None = None
    note: str | None = None
    source_id: SourceId | None = None


class ChartSeries(_Frozen):
    """One series in a bar / line chart."""

    label: str
    values: list[float]
    unit: str | None = None


class ChartStat(_Frozen):
    """One callout statistic for chart_type == 'stat'."""

    value: str
    unit: str | None = None
    label: str
    comparison: str | None = None
    source_id: SourceId | None = None


class ComparisonRow(_Frozen):
    """One row in a comparison-table chart variant."""

    axis: str
    cells: list[str]  # length must equal subjects length


class ComparisonTable(_Frozen):
    subjects: list[str]
    rows: list[ComparisonRow]


class FactsheetRow(_Frozen):
    label: str
    value: str | list[str]
    source_id: SourceId | None = None


class QuoteCard(_Frozen):
    author: str
    author_role: str
    quote: str
    sentiment: Sentiment
    stakeholder_tier: Literal["stakeholder", "adjacent", "third_party"] | None = None
    author_image_url: HttpUrl | None = None
    source_id: SourceId


# ---------------------------------------------------------------------------
# Block variants
# ---------------------------------------------------------------------------
class ParagraphBlockData(_Frozen):
    kind: Literal["paragraph"] = "paragraph"
    style: Literal["prose", "bullets"] = "prose"
    paragraphs_md: list[str] = Field(min_length=1)
    # Per-paragraph source attribution: paragraph_sources[i] is the list of
    # source_ids that ground paragraphs_md[i]. Parallel to paragraphs_md.
    # Empty list (or shorter than paragraphs_md) means "fall back to all of
    # `citations` for that paragraph" — the renderer aggregates these into a
    # cite-cluster (stacked publisher favicons + hover popover) per paragraph.
    paragraph_sources: list[list[SourceId]] = Field(default_factory=list)
    pull_quotes: list[PullQuote] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)


class TimelineBlockData(_Frozen):
    kind: Literal["timeline"] = "timeline"
    entries: list[TimelineEntry] = Field(min_length=1)
    timezone: str | None = None


class ChartBlockData(_Frozen):
    kind: Literal["chart"] = "chart"
    chart_type: Literal["bar", "stat", "compare_table"]
    series: list[ChartSeries] | None = None
    stats: list[ChartStat] | None = None
    table: ComparisonTable | None = None
    title: str | None = None


class NewsfeedBlockData(_Frozen):
    kind: Literal["newsfeed"] = "newsfeed"
    cards: list[NewsCard] = Field(min_length=1)
    variant: Literal["news", "channels", "quotes"] = "news"
    grouping: Literal["by_perspective", "by_subtopic", "by_time", "flat"] = "flat"


class FactsheetBlockData(_Frozen):
    kind: Literal["factsheet"] = "factsheet"
    rows: list[FactsheetRow] = Field(min_length=1)


class MapBlockData(_Frozen):
    kind: Literal["map"] = "map"
    locations: list[Location] = Field(min_length=1)


class ReactionsBlock(_Frozen):
    kind: Literal["reactions"] = "reactions"
    cards: list[QuoteCard] = Field(max_length=4)


class GalleryItem(_Frozen):
    image_url: HttpUrl
    caption: str = Field(min_length=1, max_length=240)
    alt_text: str | None = Field(default=None, max_length=160)
    source_url: HttpUrl | None = None


class GalleryBlockData(_Frozen):
    kind: Literal["gallery"] = "gallery"
    items: list[GalleryItem] = Field(min_length=1, max_length=12)
    citations: list[Citation] = Field(default_factory=list)


RenderBlock = Annotated[
    ParagraphBlockData
    | TimelineBlockData
    | ChartBlockData
    | NewsfeedBlockData
    | FactsheetBlockData
    | MapBlockData
    | ReactionsBlock
    | GalleryBlockData,
    Field(discriminator="kind"),
]
