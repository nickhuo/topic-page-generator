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
    - source_id (required)

The cards together must show >=2 distinct sentiments OR span stakeholder vs
third_party. A row of four cheerleaders is a fail.
"""

    def is_minimum_viable(self, data: ReactionsBlock) -> bool:
        if len(data.cards) < 2:
            return False
        sentiments = {c.sentiment for c in data.cards}
        return len(sentiments) >= 2
