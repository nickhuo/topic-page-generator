"""Render blocks — the presentation contract layer.

A Module owns *what* data is extracted (content contract). A Block owns *how*
that data is rendered (presentation contract). Modules adapt themselves into
blocks via `Module.to_block()` (added in Phase 1 cutover); templates only
consume blocks. The two layers stay orthogonal so visual changes don't ripple
into LLM prompts.
"""

from generator.blocks.converter import (
    default_block_kind,
    module_to_block,
)
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
    "default_block_kind",
    "module_to_block",
]
