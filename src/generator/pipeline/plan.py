"""Stage 3 — Plan + Aesthetic Plan. Deterministic stub."""
from __future__ import annotations

from generator.schema import (
    AestheticOverrides,
    AestheticPlanOutput,
    DisambiguationOutput,
    PlanComposition,
    PlanOutput,
    SourceStrategy,
)


def run_plan(_disamb: DisambiguationOutput) -> PlanOutput:
    return PlanOutput(
        archetype_hint="product_launch",
        layout_preset_id="product_focus",
        composition=[
            PlanComposition(
                module_kind="hero",
                artifact="HeroBanner",
                slot="hero",
                priority="required",
                artifact_alternatives=[],
            ),
            PlanComposition(
                module_kind="infobox",
                artifact="Infobox",
                slot="aside",
                priority="required",
                artifact_alternatives=[],
            ),
            PlanComposition(
                module_kind="background",
                artifact="Prose",
                slot="primary",
                priority="high",
                artifact_alternatives=[],
            ),
        ],
        source_strategy=SourceStrategy(
            preferred_tiers=["T0", "T1", "T2"],
            time_range_days=14,
            min_publishers=2,
        ),
    )


def run_aesthetic(plan: PlanOutput) -> AestheticPlanOutput:
    return AestheticPlanOutput(
        preset_id=plan.layout_preset_id,
        preset_confidence=0.88,
        alternatives_considered=["reference"],
        aesthetic_overrides=AestheticOverrides(
            palette="minimal_tech",
            density="standard",
            typography_weight="standard",
            hero_mood="minimalist_product",
            copy_register="analytical_measured",
        ),
        reasoning="stub: product launch maps to product_focus preset",
    )
