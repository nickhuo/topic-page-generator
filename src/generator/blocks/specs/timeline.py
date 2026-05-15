"""Timeline block spec — ordered, time-tagged events."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import TimelineBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class TimelineBlockSpec(BlockSpec):
    kind: ClassVar = "timeline"
    data_schema: ClassVar = TimelineBlockData
    template_path: ClassVar = "blocks/timeline.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 3 milestone entries spanning the event arc.",
        min_sources=2,
        required_facets=["start", "end_or_latest"],
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `timeline` block.

Schema:
- entries: ordered list of TimelineEntry. Each has:
    - title (<=80 chars, what happened)
    - time (ISO8601 if known, otherwise a human label like "Quarter Finals")
    - location (optional)
    - description (optional, <=160 chars)
    - importance: "breaking" | "feature" | "minor" | "normal"
    - source_id (cite where this entry's facts come from)
- timezone: IANA timezone string if entries have absolute times.

Aim for 3-7 entries. Each must be a milestone, not routine sub-event.
"""

    def is_minimum_viable(self, data: TimelineBlockData) -> bool:
        return len(data.entries) >= 2
