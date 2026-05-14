"""Reactions module — named-author quotes with sentiment."""

from __future__ import annotations

from typing import ClassVar

from generator.modules.base import Module, PlanContext
from generator.schema import ReactionsData


class ReactionsModule(Module):
    kind: ClassVar[str] = "reactions"
    serves_needs: ClassVar[list] = ["world_reaction"]
    allowed_artifacts: ClassVar[list[str]] = ["ReactionsList", "ReactionsGrid"]
    data_schema: ClassVar[type] = ReactionsData

    extraction_prompt_template: ClassVar[str] = """\
You are extracting structured data for the "Reactions" module of a news topic page.

Subject: {primary_entity}
Event type: {event_type_hint}

Evidence pool (each line is "[source_id] (tier publisher, published_at) title :: url"):
{evidence_block}

Task:
- Extract 5–15 reactions from named individuals (not anonymous sources).
- Each reaction needs: author name, author_role (e.g. "CEO, Apple"), a verbatim quote of ≤280 characters, sentiment (one of "positive", "neutral", "negative"), and source_id.
- Optionally include aggregate_sentiment counts if multiple reactions allow tallying.

Rules:
- Only quote named individuals with a verifiable role.
- Quotes must be verbatim and ≤280 characters.
- Cite every fact via a source_id that appears in the evidence pool above.
- Do not invent facts not supported by the evidence.
- Output strictly conforms to the JSON schema you've been given.
- For each reaction, set stakeholder_tier to one of:
  * "stakeholder" — person directly affected, employed by, or with formal authority over the event subject (e.g. the CEO of the company, the team captain, a head of state speaking on their own policy).
  * "adjacent" — industry expert, regulator, or competitor whose opinion materially shapes the story.
  * "third_party" — pundits, fans, generic commentators.
- Prefer stakeholders. Aim for at least 2 stakeholder items if the evidence supports it.
- Set author_image_url ONLY if an unambiguous photo URL is present in the evidence (og:image of a profile page, Wikidata image). Otherwise omit.
"""

    def queries(self, ctx: PlanContext) -> list[str]:
        entity = ctx.subject.primary_entity
        hint = ctx.subject.event_type_hint
        return [
            f"{entity} {hint} reactions response quote",
            f"{entity} experts critics fans reaction",
        ]

    def should_render(self, data: ReactionsData | None) -> bool:  # type: ignore[override]
        if data is None:
            return False
        return len(data.items) >= 3
