"""Where To Watch module — broadcast and streaming channels."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module
from generator.schema import WhereToWatchData


class WhereToWatchModule(Module):
    kind: ClassVar[str] = "where_to_watch"
    serves_needs: ClassVar[list] = ["what_can_do"]
    allowed_artifacts: ClassVar[list[str]] = ["ChannelList"]
    data_schema: ClassVar[type] = WhereToWatchData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Where To Watch" module of a news topic page.

Subject: {title}
Entities: {entities}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Extract all channels, platforms, or venues where the audience can watch or attend this event.
- Each channel needs: type (one of "tv", "streaming", "in_person", "radio", "api", "app"), name, optional region, optional url, optional cost (e.g. "Free", "$9.99/mo", "Subscription"), and source_id.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def should_render(self, data: WhereToWatchData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.channels) >= 1
