"""Schedule module — ordered list of timed events."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module
from generator.schema import ScheduleData


class ScheduleModule(Module):
    kind: ClassVar[str] = "schedule"
    serves_needs: ClassVar[list] = ["when_where", "what_next"]
    allowed_artifacts: ClassVar[list[str]] = ["ScheduleList", "ScheduleTimeline"]
    data_schema: ClassVar[type] = ScheduleData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Schedule" module of a news topic page.

Subject: {title}
Entities: {entities}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Extract all scheduled items (sessions, games, hearings, product drops, etc.) from the evidence.
- Each item needs: time_iso in ISO 8601 format, a short label, an optional location, optional duration_min, an is_milestone flag, and a source_id.
- Set timezone to the correct IANA timezone string (e.g. "America/New_York", "UTC").
- Skip items with ambiguous or unverifiable times.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Set is_milestone=true only for entries that are inflection points the reader will remember (kickoff, launch, ruling delivered, ceasefire signed). Routine sub-events should be is_milestone=false. Aim for 3–6 milestones total.
- Output strictly conforms to the JSON schema you've been given.
"""

    def should_render(self, data: ScheduleData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.items) >= 1 and bool(data.timezone)
