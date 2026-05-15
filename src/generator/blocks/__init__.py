"""Render blocks — the presentation contract layer.

A Block owns *how* data is rendered (presentation contract). Templates only
consume blocks. The two layers stay orthogonal so visual changes don't ripple
into LLM prompts.
"""

from generator.blocks.schema import (
    ChartBlockData,
    ChartSeries,
    ChartStat,
    ComparisonRow,
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

__all__ = [
    "ChartBlockData",
    "ChartSeries",
    "ChartStat",
    "ComparisonRow",
    "FactsheetBlockData",
    "FactsheetRow",
    "Location",
    "MapBlockData",
    "NewsCard",
    "NewsfeedBlockData",
    "ParagraphBlockData",
    "PullQuote",
    "RenderBlock",
    "TimelineBlockData",
    "TimelineEntry",
]
