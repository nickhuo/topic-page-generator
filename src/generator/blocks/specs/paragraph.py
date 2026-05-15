"""Paragraph block spec — prose or bullet lists."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import ParagraphBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class ParagraphBlockSpec(BlockSpec):
    kind: ClassVar = "paragraph"
    data_schema: ClassVar = ParagraphBlockData
    template_path: ClassVar = "blocks/paragraph.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least one well-cited paragraph or three bullets.",
        min_sources=2,
        min_publishers=2,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `paragraph` block.

Schema:
- style: "prose" for flowing paragraphs, "bullets" for a tight list.
- paragraphs_md: 1-4 markdown strings. For prose, each is a paragraph (60-140 words).
  For bullets, each is one bullet line (<=24 words, no leading dash).
- pull_quotes: optional 0-2 stand-out quotes from the evidence.
- citations: cite every factual claim via source_id.
"""

    def is_minimum_viable(self, data: ParagraphBlockData) -> bool:
        return any(p.strip() for p in data.paragraphs_md)
