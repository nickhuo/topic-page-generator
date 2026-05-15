"""Backbone planner — deterministic 4-section emitter.

Zero LLM calls. Emits exactly four always-on sections in canonical order:

    1. overview        → paragraph, main
    2. timeline        → timeline,  sidebar  (past / present / future)
    3. background      → paragraph, sidebar
    4. media_coverage  → newsfeed,  main     (image-only, ≤5, newest first)

Hero (title + subtitle) is rendered from `EventPage.subject` and is not a
backbone section. Acceptance criteria default to the matching BlockSpec's
`default_acceptance`; if a section needs stricter acceptance, build a new
AcceptanceCriteria here — never mutate spec defaults.
"""

from __future__ import annotations

from generator.blocks.specs import get_spec
from generator.schema import (
    AcceptanceCriteria,
    BackboneSectionId,
    BlockKind,
    EventFacts,
    Placement,
    SectionPlan,
)

# Canonical ordering. Rank assigned by position in this list.
_BACKBONE_ORDER: tuple[BackboneSectionId, ...] = (
    "overview",
    "timeline",
    "background",
    "media_coverage",
)

_BLOCK_KIND_FOR_ID: dict[BackboneSectionId, BlockKind] = {
    "overview": "paragraph",
    "timeline": "timeline",
    "background": "paragraph",
    "media_coverage": "newsfeed",
}

_PLACEMENT_FOR_ID: dict[BackboneSectionId, Placement] = {
    "overview": "main",
    "timeline": "sidebar",
    "background": "sidebar",
    "media_coverage": "main",
}

_TITLES: dict[BackboneSectionId, str] = {
    "overview": "Overview",
    "timeline": "Timeline",
    "background": "Background",
    "media_coverage": "Media coverage",
}


def _intent_for(section_id: BackboneSectionId, canonical_title: str) -> str:
    return {
        "overview": (
            f"Two short paragraphs introducing {canonical_title}: what just "
            f"happened, who is involved, when/where, and why a reader should care."
        ),
        "timeline": (
            "Three to seven milestone entries spanning past, present, and "
            "future. Every entry must set `temporal_phase` to one of past / "
            "present / future. The set MUST cover all three phases when "
            "evidence supports it — at least one entry for events that "
            "already happened (past), the current/just-broken development "
            "(present), and any scheduled or expected next steps (future)."
        ),
        "background": (
            "Two short paragraphs of context the reader needs to understand "
            "why this event matters — prior history, structural setup, or "
            "the slow build-up. Concise — this renders in the sidebar."
        ),
        "media_coverage": (
            "Up to five high-signal external articles from distinct publishers, "
            "biased toward T0/T1 outlets. Every card MUST have a thumbnail_url "
            "— drop cards without images. Sort newest first by published_at."
        ),
    }[section_id]


def _acceptance_for(
    section_id: BackboneSectionId, default: AcceptanceCriteria
) -> AcceptanceCriteria:
    """Tighten acceptance on top of the spec default where the backbone needs it."""
    if section_id == "timeline":
        return AcceptanceCriteria(
            description=(
                "At least 3 milestone entries with temporal_phase set; the set "
                "should cover past / present / future when sources allow."
            ),
            min_sources=default.min_sources,
            min_publishers=default.min_publishers,
            required_facets=["past", "present", "future"],
            forbid_single_perspective=default.forbid_single_perspective,
        )
    if section_id == "media_coverage":
        return AcceptanceCriteria(
            description=(
                "Up to 5 image-bearing cards from distinct publishers, sorted "
                "newest first."
            ),
            min_sources=default.min_sources,
            min_publishers=default.min_publishers,
            required_facets=["thumbnail_url"],
            forbid_single_perspective=default.forbid_single_perspective,
        )
    return default


def build_backbone_sections(
    facts: EventFacts, canonical_title: str
) -> list[SectionPlan]:
    """Return the 4 always-on backbone sections in canonical rank order."""
    sections: list[SectionPlan] = []
    for rank, section_id in enumerate(_BACKBONE_ORDER, start=1):
        block_kind = _BLOCK_KIND_FOR_ID[section_id]
        spec_cls = get_spec(block_kind)
        acceptance = _acceptance_for(section_id, spec_cls.default_acceptance)
        sections.append(
            SectionPlan(
                section_id=section_id,
                kind="backbone",
                title=_TITLES[section_id],
                rank=rank,
                block_kind=block_kind,
                intent=_intent_for(section_id, canonical_title),
                acceptance=acceptance,
                placement=_PLACEMENT_FOR_ID[section_id],
            )
        )
    return sections


__all__ = ["build_backbone_sections"]
