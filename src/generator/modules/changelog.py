"""Changelog module — versioned list of changes or updates."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module, PlanContext
from generator.schema import ChangelogData


class ChangelogModule(Module):
    kind: ClassVar[str] = "changelog"
    serves_needs: ClassVar[list] = ["what_happened", "why_matters"]
    allowed_artifacts: ClassVar[list[str]] = ["Changelog"]
    data_schema: ClassVar[type] = ChangelogData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Changelog" module of a news topic page.

Subject: {primary_entity}
Event type: {event_type_hint}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Set version_label to the version, edition, or release name being discussed.
- Set previous_version_label if the evidence mentions what changed since a prior version.
- Extract individual changes as entries, each with:
  - label: short feature or change name
  - description: ≤80 words describing the change
  - importance: one of "breaking", "feature", or "minor"
  - source_id: from the evidence pool above

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def queries(self, ctx: PlanContext) -> list[str]:
        entity = ctx.subject.primary_entity
        hint = ctx.subject.event_type_hint
        return [
            f"{entity} {hint} changelog what's new release notes",
            f"{entity} changes updates features",
        ]

    def should_render(self, data: ChangelogData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.entries) >= 1
