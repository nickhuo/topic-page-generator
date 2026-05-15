"""Infobox module — structured key-fact rows for a topic."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module
from generator.schema import InfoboxData


class InfoboxModule(Module):
    kind: ClassVar[str] = "infobox"
    serves_needs: ClassVar[list] = ["when_where", "who_involved"]
    allowed_artifacts: ClassVar[list[str]] = ["Infobox"]
    data_schema: ClassVar[type] = InfoboxData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Infobox" module of a news topic page.

Subject: {title}
Entities: {entities}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Produce 5–9 key-fact rows covering who, what, when, where, why for the event.
- Each row must have a short label (e.g. "Date", "Venue", "Organizer"), a concise value, and a source_id.
- Every row's source_id MUST appear in the evidence pool above.
- Prefer specific, verifiable facts over general descriptions.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def should_render(self, data: InfoboxData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.rows) >= 3
