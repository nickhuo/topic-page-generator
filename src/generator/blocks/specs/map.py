"""Map block spec — locations with coordinates."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import MapBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class MapBlockSpec(BlockSpec):
    kind: ClassVar = "map"
    data_schema: ClassVar = MapBlockData
    template_path: ClassVar = "blocks/map.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least one geocoded location.",
        min_sources=1,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `map` block.

Schema:
- locations: 1-6 Location. Each has:
    - name (place label)
    - lat / lon (decimal degrees; both required to render a pin)
    - note (<=80 chars, what happened here?)
    - source_id

Only include locations whose coordinates you can verify from evidence.
"""

    def is_minimum_viable(self, data: MapBlockData) -> bool:
        return any(
            loc.lat is not None and loc.lon is not None for loc in data.locations
        )
