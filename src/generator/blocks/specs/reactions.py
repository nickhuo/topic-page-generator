"""Reactions block spec — up to 4 quote cards across multiple sentiments."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import ReactionsBlock
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class ReactionsBlockSpec(BlockSpec):
    kind: ClassVar = "reactions"
    data_schema: ClassVar = ReactionsBlock
    template_path: ClassVar = "blocks/reactions.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 2 quotes spanning >= 2 sentiments or stakeholder tiers.",
        min_sources=2,
        min_publishers=2,
        forbid_single_perspective=True,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `reactions` block.

Schema:
- cards: 2-4 QuoteCard. Each has:
    - author, author_role
    - quote (verbatim, <=240 chars; do NOT paraphrase)
    - sentiment: "positive" | "neutral" | "negative"
    - stakeholder_tier: "stakeholder" | "adjacent" | "third_party"
    - author_image_url (optional)
    - source_id (required — for trace integrity)
    - article_title (REQUIRED — the headline of the source article the
      quote came from, verbatim)
    - article_url (REQUIRED — direct link to that article; the whole card
      surface becomes a link to this URL)
    - publisher (REQUIRED — publisher name as it appears in the source)
    - publisher_logo_url (optional — favicon / mark URL if present in the
      evidence; do NOT invent)

The cards together must show >=2 distinct sentiments OR span stakeholder vs
third_party. A row of four cheerleaders is a fail.

Quotes render as a card that links straight to `article_url` (no numeric
[N] citation anchor). If you cannot find a real `article_url` for a quote,
DROP that card — do not synthesize a URL.
"""

    def is_minimum_viable(self, data: ReactionsBlock) -> bool:
        if len(data.cards) < 2:
            return False
        sentiments = {c.sentiment for c in data.cards}
        return len(sentiments) >= 2
