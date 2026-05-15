"""Media Coverage module — distinct headlines from across the press."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module
from generator.schema import MediaCoverageData


class MediaCoverageModule(Module):
    kind: ClassVar[str] = "media_coverage"
    serves_needs: ClassVar[list] = ["world_reaction", "current_state"]
    allowed_artifacts: ClassVar[list[str]] = ["CoverageList"]
    data_schema: ClassVar[type] = MediaCoverageData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Media Coverage" module of a news topic page.

Subject: {title}
Entities: {entities}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- List 5–12 distinct headlines from different publishers covering this event.
- Each item needs: headline, publisher name, publisher_tier (T0/T1/T2/T3), published_at (ISO 8601), url, a snippet of ≤30 words, optional perspective ("favorable"/"critical"/"neutral"), optional sub_topic, and source_id.
- Set grouping_strategy to one of: "by_perspective", "by_subtopic", "by_time", "flat".

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def should_render(self, data: MediaCoverageData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.items) >= 3
