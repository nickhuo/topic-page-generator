"""Deterministic event-type → plan-skeleton lookup.

Each archetype declares which module kinds appear on the page, what
artifact renders them, which slot they occupy, what priority they have,
which layout preset to start with, and the default source strategy.

PR 4 will use this to drive Stage 5 extraction (one module per composition
entry). PR 5 will use the slot routing + preset for layout assembly.
"""
from __future__ import annotations

from generator.schema import (
    AestheticPresetId,
    PlanComposition,
    PlanOutput,
    SourceStrategy,
)


def _mk(
    archetype: str,
    preset: AestheticPresetId,
    composition: list[PlanComposition],
    strategy: SourceStrategy,
) -> PlanOutput:
    return PlanOutput(
        archetype_hint=archetype,
        layout_preset_id=preset,
        composition=composition,
        source_strategy=strategy,
    )


ARCHETYPES: dict[str, PlanOutput] = {
    "product_launch": _mk(
        archetype="product_launch",
        preset="product_focus",
        composition=[
            PlanComposition(module_kind="hero", artifact="HeroBanner", slot="hero", priority="required"),
            PlanComposition(module_kind="infobox", artifact="Infobox", slot="aside", priority="required"),
            PlanComposition(module_kind="changelog", artifact="ChangelogList", slot="primary", priority="high"),
            PlanComposition(module_kind="kpi_numbers", artifact="KPITiles", slot="primary", priority="medium"),
            PlanComposition(module_kind="comparison", artifact="ComparisonTable", slot="primary", priority="medium"),
            PlanComposition(module_kind="official_statements", artifact="QuoteStack", slot="primary", priority="medium"),
            PlanComposition(module_kind="media_coverage", artifact="CoverageList", slot="tail", priority="medium"),
            PlanComposition(module_kind="background", artifact="Prose", slot="primary", priority="low"),
        ],
        strategy=SourceStrategy(
            preferred_tiers=["T0", "T1", "T2"],
            time_range_days=14,
            min_publishers=2,
        ),
    ),
    "live_cultural_event": _mk(
        archetype="live_cultural_event",
        preset="live_dominance",
        composition=[
            PlanComposition(module_kind="hero", artifact="HeroBanner", slot="hero", priority="required"),
            PlanComposition(module_kind="infobox", artifact="Infobox", slot="aside", priority="required"),
            PlanComposition(module_kind="schedule", artifact="Timeline", slot="primary", priority="required"),
            PlanComposition(module_kind="where_to_watch", artifact="ChannelGrid", slot="primary", priority="high"),
            PlanComposition(module_kind="reactions", artifact="ReactionStream", slot="primary", priority="high"),
            PlanComposition(module_kind="media_coverage", artifact="CoverageList", slot="tail", priority="medium"),
            PlanComposition(module_kind="background", artifact="Prose", slot="primary", priority="low"),
        ],
        strategy=SourceStrategy(
            preferred_tiers=["T0", "T1"],
            time_range_days=7,
            min_publishers=3,
        ),
    ),
    "scheduled_sports_event": _mk(
        archetype="scheduled_sports_event",
        preset="imminent_event",
        composition=[
            PlanComposition(module_kind="hero", artifact="HeroBanner", slot="hero", priority="required"),
            PlanComposition(module_kind="infobox", artifact="Infobox", slot="aside", priority="required"),
            PlanComposition(module_kind="countdown", artifact="CountdownBlock", slot="hero", priority="required"),
            PlanComposition(module_kind="schedule", artifact="Timeline", slot="primary", priority="high"),
            PlanComposition(module_kind="where_to_watch", artifact="ChannelGrid", slot="primary", priority="high"),
            PlanComposition(module_kind="media_coverage", artifact="CoverageList", slot="tail", priority="medium"),
            PlanComposition(module_kind="background", artifact="Prose", slot="primary", priority="low"),
        ],
        strategy=SourceStrategy(
            preferred_tiers=["T0", "T1", "T2"],
            time_range_days=30,
            min_publishers=2,
        ),
    ),
    "generic_event": _mk(
        archetype="generic_event",
        preset="reference",
        composition=[
            PlanComposition(module_kind="hero", artifact="HeroBanner", slot="hero", priority="required"),
            PlanComposition(module_kind="infobox", artifact="Infobox", slot="aside", priority="high"),
            PlanComposition(module_kind="media_coverage", artifact="CoverageList", slot="primary", priority="medium"),
            PlanComposition(module_kind="background", artifact="Prose", slot="primary", priority="low"),
        ],
        strategy=SourceStrategy(
            preferred_tiers=["T1", "T2", "T0"],
            time_range_days=14,
            min_publishers=2,
        ),
    ),
}


def lookup(event_type_hint: str | None) -> PlanOutput:
    """Return the plan skeleton for `event_type_hint`, falling through to generic."""
    if not event_type_hint:
        return ARCHETYPES["generic_event"]
    return ARCHETYPES.get(event_type_hint, ARCHETYPES["generic_event"])
