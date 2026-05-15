"""Hero module — primary identity card for the event/entity."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module
from generator.schema import HeroData


class HeroModule(Module):
    kind: ClassVar[str] = "hero"
    serves_needs: ClassVar[list] = ["what_happened"]
    allowed_artifacts: ClassVar[list[str]] = ["HeroBanner", "HeroSplit", "HeroTextOnly"]
    data_schema: ClassVar[type] = HeroData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Hero" module of a news topic page.

Subject: {title}
Entities: {entities}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Write a title of ≤80 characters that captures the core event.
- Write a subtitle of ≤120 characters (optional, add only if it adds meaningful context).
- Write a one-sentence summary of ≤140 characters that conveys the essential fact.
- Set badge_label to match the temporal posture (e.g., "LIVE", "UPCOMING", "JUST IN", "RECAP").
- Write 3–4 overview_bullets, each ≤18 words. Each bullet must cite a source_id from the evidence pool. Bullets should be the four things a reader most needs to know about this event at a glance — not a restatement of the title.
- Every claim must be supported by the evidence pool above.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def should_render(self, data: HeroData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return bool(data.title and data.summary)
