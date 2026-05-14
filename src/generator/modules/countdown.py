"""Countdown module — single anchoring future timestamp."""
from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module, PlanContext
from generator.schema import CountdownData


class CountdownModule(Module):
    kind: ClassVar[str] = "countdown"
    serves_needs: ClassVar[list] = ["what_next"]
    allowed_artifacts: ClassVar[list[str]] = ["Countdown"]
    data_schema: ClassVar[type] = CountdownData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Countdown" module of a news topic page.

Subject: {primary_entity}
Event type: {event_type_hint}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Identify the single most important upcoming moment related to this event.
- Set target_at to the ISO 8601 timestamp for that moment.
- Set label to a short human-readable description of what happens at that time.
- Provide the source_id from the evidence pool that confirms this timestamp.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def queries(self, ctx: PlanContext) -> list[str]:
        entity = ctx.subject.primary_entity
        hint = ctx.subject.event_type_hint
        return [
            f"{entity} {hint} date time when",
            f"{entity} upcoming launch start",
        ]

    def should_render(self, data: CountdownData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return data.target_at is not None
