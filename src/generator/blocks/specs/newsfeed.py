"""Newsfeed block spec — a list of external link cards."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import NewsfeedBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class NewsfeedBlockSpec(BlockSpec):
    kind: ClassVar = "newsfeed"
    data_schema: ClassVar = NewsfeedBlockData
    template_path: ClassVar = "blocks/newsfeed.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 3 cards from distinct publishers.",
        min_sources=3,
        min_publishers=3,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `newsfeed` block.

Schema:
- variant: "news" (default), "channels" (where-to-watch), or "quotes".
- grouping: "by_perspective" | "by_subtopic" | "by_time" | "flat".
- cards: 3-8 NewsCard. Each has url, title, publisher, tier, published_at?,
  thumbnail_url?, summary?, source_id?.

Pick `variant` + `grouping` to match section intent. Prefer T0/T1 publishers.
Do not repeat the same publisher more than twice.
"""

    def is_minimum_viable(self, data: NewsfeedBlockData) -> bool:
        return len(data.cards) >= 2
