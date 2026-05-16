"""Latest news block spec — vertical stack of landscape-composition cards."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import LatestNewsBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria

LATEST_NEWS_MAX_CARDS = 15
LATEST_NEWS_MIN_CARDS = 4
# Cards rendered immediately; the rest are revealed in batches by the
# "Load more" button. Keep in sync with templates/blocks/latest_news.html
# and the click handler in templates/toc.js.
LATEST_NEWS_INITIAL_VISIBLE = 5


class LatestNewsBlockSpec(BlockSpec):
    kind: ClassVar = "latest_news"
    data_schema: ClassVar = LatestNewsBlockData
    template_path: ClassVar = "blocks/latest_news.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description=(
            "Vertical list of 4-8 recent news items from distinct publishers, "
            "newest first. Each card links directly to the source article."
        ),
        min_sources=4,
        min_publishers=3,
        required_facets=["published_at"],
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `latest_news` block.

Schema:
- cards: 4-15 NewsCard. Each has url, title, publisher, tier, published_at?,
  thumbnail_url?, summary?, source_id?. The first 5 render immediately; the
  rest sit behind a "Load more" button, so prefer breadth over a tight
  top-5 — extras with weaker timeliness are still useful below the fold.

HARD RULES — the pipeline post-filters; obey them up front to avoid loss:
- Every card MUST have `published_at` (ISO8601). Cards without a date drop.
- Every card MUST have a `url` pointing at the original article — the whole
  card surface becomes a link to that URL.
- Order cards by `published_at` DESCENDING (newest first).
- `summary` is one neutral sentence (<=220 chars). NO analytical framing,
  NO hedging, NO editorializing. If unsure, omit `summary`.
- Prefer newswire / reporting outlets over opinion pieces and press releases.
- Do not repeat the same publisher more than twice.

Pick `thumbnail_url` VERBATIM from the matching evidence `<src>` block's
`image_url:` line when available; do NOT invent URLs and do NOT reuse the
article URL.
"""

    def postprocess(self, data: LatestNewsBlockData) -> LatestNewsBlockData:
        # Require a date; sort newest-first; cap at the max.
        filtered = [c for c in data.cards if c.published_at]
        filtered.sort(key=lambda c: c.published_at or "", reverse=True)
        capped = filtered[:LATEST_NEWS_MAX_CARDS]
        if not capped:
            # min_length=1 on the schema — keep one so Pydantic validates;
            # viability check below will drop the section.
            capped = list(data.cards[:1])
        if capped == list(data.cards):
            return data
        return data.model_copy(update={"cards": capped})

    def is_minimum_viable(self, data: LatestNewsBlockData) -> bool:
        dated = [c for c in data.cards if c.published_at]
        if len(dated) < LATEST_NEWS_MIN_CARDS:
            return False
        publishers = {c.publisher for c in dated if c.publisher}
        return len(publishers) >= 2
