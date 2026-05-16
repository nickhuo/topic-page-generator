"""Render-block schemas — discriminated by `kind`.

Block kinds map 1:1 to templates under `templates/blocks/`:
  paragraph / timeline (sidebar-only) / chart / newsfeed / reactions / gallery

Module subclasses produce one of these via `to_block()`. Templates consume
only blocks, never raw module data. `timeline` blocks are emitted exclusively
by the backbone planner with placement="sidebar"; curation must never propose
a timeline section.
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


class QuoteCard(_Frozen):
    author: str
    author_role: str
    quote: str
    sentiment: Sentiment
    stakeholder_tier: Literal["stakeholder", "adjacent", "third_party"] | None = None
    author_image_url: HttpUrl | None = None
    source_id: SourceId
    # Article attribution — when present, the whole card links to article_url
    # (replaces the previous numeric [N] anchor citation).
    article_title: str | None = None
    article_url: HttpUrl | None = None
    publisher: str | None = None
    publisher_logo_url: HttpUrl | None = None


class PersonCard(_Frozen):
    """A single person profile in a `people` block."""

    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=120)
    bio: str = Field(min_length=1, max_length=260)
    image_url: HttpUrl | None = None
    image_source: Literal["wikipedia", "wikidata", "brave", "none"] = "none"
    image_credit_url: HttpUrl | None = None
    profile_url: HttpUrl | None = None  # Wikipedia / official page
    source_ids: list[SourceId] = Field(default_factory=list)


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


class LatestNewsBlockData(_Frozen):
    """A vertical stack of landscape-composition news cards.

    Distinct from `newsfeed` (horizontal scroll carousel): rendered as a
    full-width vertical list, intended as a closing "Latest news" section.
    Reuses `NewsCard` as the per-item shape.
    """

    kind: Literal["latest_news"] = "latest_news"
    cards: list[NewsCard] = Field(min_length=1, max_length=8)


class PeopleBlockData(_Frozen):
    """Profile cards for "Who is involved" needs."""

    kind: Literal["people"] = "people"
    cards: list[PersonCard] = Field(min_length=2, max_length=6)


RenderBlock = Annotated[
    ParagraphBlockData
    | TimelineBlockData
    | ChartBlockData
    | NewsfeedBlockData
    | ReactionsBlock
    | GalleryBlockData
    | LatestNewsBlockData
    | PeopleBlockData,
    Field(discriminator="kind"),
]
