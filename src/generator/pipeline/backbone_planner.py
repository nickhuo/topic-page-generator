"""Backbone planner — deterministic 6-section emitter.

Zero LLM calls. Maps the 6 always-on backbone section IDs to canonical
titles, intents, block kinds, and ranks. Acceptance criteria default to the
matching BlockSpec's `default_acceptance` so the research loop (Plan 3) has
something to measure against.

If a section needs stricter acceptance than the spec default, build a new
AcceptanceCriteria here — never mutate spec defaults.
"""

from __future__ import annotations

from generator.blocks.specs import get_spec
from generator.schema import (
    AcceptanceCriteria,
    BackboneSectionId,
    BlockKind,
    EventFacts,
    SectionPlan,
)

# Canonical ordering. Rank assigned by position in this list.
_BACKBONE_ORDER: tuple[BackboneSectionId, ...] = (
    "overview",
    "key_takeaways",
    "timeline",
    "key_facts",
    "background",
    "media_coverage",
)

_BLOCK_KIND_FOR_ID: dict[BackboneSectionId, BlockKind] = {
    "overview": "paragraph",
    "key_takeaways": "paragraph",
    "timeline": "timeline",
    "key_facts": "factsheet",
    "background": "paragraph",
    "media_coverage": "newsfeed",
}

_TITLES: dict[BackboneSectionId, str] = {
    "overview": "Overview",
    "key_takeaways": "Key takeaways",
    "timeline": "Timeline",
    "key_facts": "Key facts",
    "background": "Background",
    "media_coverage": "Media coverage",
}


def _intent_for(section_id: BackboneSectionId, canonical_title: str) -> str:
    return {
        "overview": (
            f"Two short paragraphs introducing {canonical_title}: what just "
            f"happened, who is involved, when/where, and why a reader should care."
        ),
        "key_takeaways": (
            "Three to five tight bullets surfacing the most consequential facts. "
            "Each bullet is a standalone claim — no narrative."
        ),
        "timeline": (
            "Three to seven milestone entries tracing the event arc from earliest "
            "verifiable trigger to the most recent development."
        ),
        "key_facts": (
            "Labeled key/value facts (date, location, principals, headline numbers). "
            "Skip rows where the value is unknown."
        ),
        "background": (
            "Two paragraphs of context the reader needs to understand why this event "
            "matters — prior history, structural setup, or the slow build-up."
        ),
        "media_coverage": (
            "Three to eight high-signal external articles from distinct publishers, "
            "biased toward T0/T1 outlets, ordered by recency."
        ),
    }[section_id]


def build_backbone_sections(
    facts: EventFacts, canonical_title: str
) -> list[SectionPlan]:
    """Return the 6 always-on backbone sections in canonical rank order."""
    sections: list[SectionPlan] = []
    for rank, section_id in enumerate(_BACKBONE_ORDER, start=1):
        block_kind = _BLOCK_KIND_FOR_ID[section_id]
        spec_cls = get_spec(block_kind)
        acceptance: AcceptanceCriteria = spec_cls.default_acceptance
        sections.append(
            SectionPlan(
                section_id=section_id,
                kind="backbone",
                title=_TITLES[section_id],
                rank=rank,
                block_kind=block_kind,
                intent=_intent_for(section_id, canonical_title),
                acceptance=acceptance,
            )
        )
    return sections


__all__ = ["build_backbone_sections"]
