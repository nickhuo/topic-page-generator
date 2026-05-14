"""Background module — synthesized context paragraphs."""
from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module, PlanContext
from generator.schema import BackgroundData


class BackgroundModule(Module):
    kind: ClassVar[str] = "background"
    serves_needs: ClassVar[list] = ["what_happened", "why_matters"]
    allowed_artifacts: ClassVar[list[str]] = ["Prose"]
    data_schema: ClassVar[type] = BackgroundData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Background" module of a news topic page.

Subject: {primary_entity}
Event type: {event_type_hint}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
Synthesize 1–2 paragraphs (≤200 words total) of background using ONLY the provided Tavily snippets and Wikidata facts. There is NO Wikipedia source available. Every paragraph's `citations[]` MUST list at least one source_id from the evidence. Do not invent dates or names.

Rules:
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
"""

    def queries(self, ctx: PlanContext) -> list[str]:
        entity = ctx.subject.primary_entity
        hint = ctx.subject.event_type_hint
        return [
            f"{entity} background history context",
            f"{entity} {hint} overview explainer",
        ]

    def should_render(self, data: BackgroundData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.paragraphs) >= 1 and all(
            p.citations for p in data.paragraphs
        )
