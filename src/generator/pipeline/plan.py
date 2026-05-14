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

    Uses triage's event_type_hint as the primary signal. Disambiguation may
    refine the entity/time anchor but the archetype classification comes from
    triage.
    """
    return _lookup_archetype(triage.event_type_hint)


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
