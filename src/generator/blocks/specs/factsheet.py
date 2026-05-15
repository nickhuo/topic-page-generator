"""Factsheet block spec — labeled key/value pairs (infobox-style)."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import FactsheetBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class FactsheetBlockSpec(BlockSpec):
    kind: ClassVar = "factsheet"
    data_schema: ClassVar = FactsheetBlockData
    template_path: ClassVar = "blocks/factsheet.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 3 high-signal labeled facts.",
        min_sources=2,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `factsheet` block.

Schema:
- rows: 3-8 FactsheetRow. Each has:
    - label: short noun phrase (<=24 chars), e.g. "Date", "Location", "CEO".
    - value: a string OR list of strings (for multi-value facts).
    - source_id: cite the row.

Order rows by descending importance. Skip rows where the value is unknown.
"""

    def is_minimum_viable(self, data: FactsheetBlockData) -> bool:
        return len(data.rows) >= 3
