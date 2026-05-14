"""Stage 3 — Plan (deterministic) + Aesthetic Plan (LLM)."""
from __future__ import annotations

import logging

from generator.llm.client import call_structured, get_default_model
from generator.pipeline.archetype_table import lookup as _lookup_archetype
from generator.prompts.aesthetic import build_aesthetic_messages
from generator.schema import (
    AestheticPlanOutput,
    DisambiguationOutput,
    PlanOutput,
    TriageOutput,
)

log = logging.getLogger(__name__)

AESTHETIC_CONFIDENCE_THRESHOLD = 0.75


def run_plan_stage(triage: TriageOutput, disamb: DisambiguationOutput) -> PlanOutput:
    """Deterministic Stage 3a: event type → archetype lookup.

    Prefer the disambiguated event_type_hint if disambiguation actually chose one.
    When triage is confident, disamb short-circuits and copies triage.event_type_hint.
    When triage is low-confidence and disamb LLM-resolves, disamb's hint is more authoritative.
    """
    # Prefer the disambiguated event_type_hint if disambiguation actually chose one.
    chosen_hint = (
        disamb.chosen.event_type_hint
        if disamb.chosen is not None
        else triage.event_type_hint
    )
    return _lookup_archetype(chosen_hint)


async def run_aesthetic_stage(
    triage: TriageOutput,
    plan: PlanOutput,
    evidence_preview: str,
    *,
    model: str | None = None,
) -> AestheticPlanOutput:
    """LLM Stage 3b: pick aesthetic preset + closed-enum overrides."""
    out = await call_structured(
        model=model or get_default_model("aesthetic"),
        messages=build_aesthetic_messages(triage, plan, evidence_preview),
        response_model=AestheticPlanOutput,
    )

    if out.preset_confidence < AESTHETIC_CONFIDENCE_THRESHOLD:
        log.warning(
            "Aesthetic preset_confidence %.2f < %.2f; falling back to 'reference'.",
            out.preset_confidence,
            AESTHETIC_CONFIDENCE_THRESHOLD,
        )
        # Replace preset_id with the safe default; keep the LLM's reasoning.
        out = out.model_copy(update={"preset_id": "reference"})
    return out
