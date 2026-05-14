"""Comparison module — side-by-side table of 2–3 subjects across N axes."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module, PlanContext
from generator.schema import ComparisonData


class ComparisonModule(Module):
    kind: ClassVar[str] = "comparison"
    serves_needs: ClassVar[list] = ["who_involved", "why_matters"]
    allowed_artifacts: ClassVar[list[str]] = ["ComparisonTable"]
    data_schema: ClassVar[type] = ComparisonData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Comparison" module of a news topic page.

Subject: {primary_entity}
Event type: {event_type_hint}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Identify 2–3 subjects (e.g. candidates, products, teams, proposals) to compare.
- Define meaningful axes of comparison (e.g. price, performance, stance, record).
- For each axis, provide a cell value and source_id for every subject.
- The cells list in each axis MUST have the same length as the subjects list.

Rules:
- Each cell's source_id MUST appear in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def queries(self, ctx: PlanContext) -> list[str]:
        entity = ctx.subject.primary_entity
        hint = ctx.subject.event_type_hint
        return [
            f"{entity} {hint} comparison versus",
            f"{entity} competitors alternatives comparison",
        ]

    def should_render(self, data: ComparisonData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return (
            len(data.subjects) >= 2
            and len(data.axes) >= 1
            and all(len(a.cells) == len(data.subjects) for a in data.axes)
        )
