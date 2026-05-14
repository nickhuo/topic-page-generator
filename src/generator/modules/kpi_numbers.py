"""KPI Numbers module — 1–4 quantitative tiles."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module, PlanContext
from generator.schema import KPINumbersData


class KPINumbersModule(Module):
    kind: ClassVar[str] = "kpi_numbers"
    serves_needs: ClassVar[list] = ["current_state", "why_matters"]
    allowed_artifacts: ClassVar[list[str]] = ["KPITiles"]
    data_schema: ClassVar[type] = KPINumbersData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "KPI Numbers" module of a news topic page.

Subject: {primary_entity}
Event type: {event_type_hint}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Extract 1–4 compelling quantitative claims from the evidence.
- Each tile needs: value (the number as a string), optional unit, a short label, optional comparison (e.g. "up 12% YoY"), and a source_id.
- Choose the most impactful metrics — market size, attendance, revenue, scores, counts, etc.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def queries(self, ctx: PlanContext) -> list[str]:
        entity = ctx.subject.primary_entity
        hint = ctx.subject.event_type_hint
        return [
            f"{entity} {hint} numbers statistics data",
            f"{entity} metrics revenue attendance figures",
        ]

    def should_render(self, data: KPINumbersData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return 1 <= len(data.tiles) <= 4
