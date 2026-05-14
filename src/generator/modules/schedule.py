"""Schedule module — ordered list of timed events."""
from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module, PlanContext
from generator.schema import ScheduleData


class ScheduleModule(Module):
    kind: ClassVar[str] = "schedule"
    serves_needs: ClassVar[list] = ["when_where", "what_next"]
    allowed_artifacts: ClassVar[list[str]] = ["ScheduleList", "ScheduleTimeline"]
    data_schema: ClassVar[type] = ScheduleData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Schedule" module of a news topic page.

Subject: {primary_entity}
Event type: {event_type_hint}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Extract all scheduled items (sessions, games, hearings, product drops, etc.) from the evidence.
- Each item needs: time_iso in ISO 8601 format, a short label, an optional location, optional duration_min, and a source_id.
- Set timezone to the correct IANA timezone string (e.g. "America/New_York", "UTC").
- Skip items with ambiguous or unverifiable times.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def queries(self, ctx: PlanContext) -> list[str]:
        entity = ctx.subject.primary_entity
        hint = ctx.subject.event_type_hint
        return [
            f"{entity} {hint} schedule dates times",
            f"{entity} agenda calendar",
        ]

    def should_render(self, data: ScheduleData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.items) >= 1 and bool(data.timezone)
