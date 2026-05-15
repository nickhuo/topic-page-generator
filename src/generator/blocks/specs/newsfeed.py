"""Newsfeed block spec — a list of external link cards."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import NewsfeedBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria

# Maximum number of cards rendered in a newsfeed block. The template assumes
# this cap (CSS scroll-snap carousel sized for ~5 cards).
NEWSFEED_MAX_CARDS = 5


class NewsfeedBlockSpec(BlockSpec):
    kind: ClassVar = "newsfeed"
    data_schema: ClassVar = NewsfeedBlockData
    template_path: ClassVar = "blocks/newsfeed.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="Up to 5 image-bearing cards from distinct publishers, newest first.",
        min_sources=3,
        min_publishers=3,
        required_facets=["thumbnail_url"],
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `newsfeed` block.

Schema:
- variant: "news" (default), "channels" (where-to-watch), or "quotes".
- grouping: "by_perspective" | "by_subtopic" | "by_time" | "flat".
- cards: 3-8 NewsCard. Each has url, title, publisher, tier, published_at?,
  thumbnail_url?, summary?, source_id?.

HARD RULES — the pipeline post-filters; obey them up front to avoid loss:
- Every card MUST have a `thumbnail_url`. Sources without an image are
  silently dropped after extraction, so do not emit them.
- Every card MUST have a `published_at` (ISO8601). Cards without a date are
  dropped.
- Order cards by `published_at` DESCENDING (newest first).
- Emit at most 5 cards. If more than 5 qualifying sources exist, pick the 5
  most recent from the most authoritative distinct publishers.

Pick `variant` + `grouping` to match section intent. Prefer T0/T1 publishers.
Do not repeat the same publisher more than twice.
"""

    def postprocess(self, data: NewsfeedBlockData) -> NewsfeedBlockData:
        # Image-only + dated, sorted newest-first, capped at NEWSFEED_MAX_CARDS.
        filtered = [
            c for c in data.cards if c.thumbnail_url is not None and c.published_at
        ]
        filtered.sort(key=lambda c: c.published_at or "", reverse=True)
        capped = filtered[:NEWSFEED_MAX_CARDS]
        if capped == list(data.cards):
            return data
        # min_length=1 on NewsfeedBlockData.cards — if everything got filtered,
        # keep at least one card so the Pydantic model validates. Viability
        # check below will then drop the whole section.
        if not capped:
            capped = list(data.cards[:1])
        return data.model_copy(update={"cards": capped})

    def is_minimum_viable(self, data: NewsfeedBlockData) -> bool:
        image_bearing = [c for c in data.cards if c.thumbnail_url is not None]
        return len(image_bearing) >= 3
