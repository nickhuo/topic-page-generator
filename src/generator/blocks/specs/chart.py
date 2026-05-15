"""Chart block spec — stat callouts, bar series, or compare tables."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import ChartBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class ChartBlockSpec(BlockSpec):
    kind: ClassVar = "chart"
    data_schema: ClassVar = ChartBlockData
    template_path: ClassVar = "blocks/chart.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least one quantitative payload (stat/series/table).",
        min_sources=1,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `chart` block.

Choose ONE chart_type and fill the matching field:
- "stat": fill `stats` with 1-4 ChartStat (value, unit?, label, comparison?, source_id).
- "bar": fill `series` with 1-3 ChartSeries (label, values, unit?).
- "compare_table": fill `table` with ComparisonTable (subjects, rows).

Only the chosen field is required; leave others null.
Cite every number via source_id.
"""

    def is_minimum_viable(self, data: ChartBlockData) -> bool:
        if data.chart_type == "stat":
            return bool(data.stats)
        if data.chart_type == "bar":
            return bool(data.series)
        if data.chart_type == "compare_table":
            return data.table is not None and bool(data.table.rows)
        return False
