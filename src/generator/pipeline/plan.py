"""Stage 3 — Plan (LLM, needs-driven) + Aesthetic Plan (LLM)."""

from __future__ import annotations

import logging

from generator.llm.client import call_structured, get_default_model
from generator.prompts.aesthetic import build_aesthetic_messages
from generator.prompts.plan import build_need_plan_messages
from generator.schema import (
    AestheticPlanOutput,
    DisambiguationOutput,
    NeedCurationPlan,
    NeedPlanOutput,
    TriageOutput,
)

log = logging.getLogger(__name__)

AESTHETIC_CONFIDENCE_THRESHOLD = 0.75

_OPINION_MODULES = {"reactions", "media_coverage", "official_statements"}


def infer_default_category(assigned_modules: list[str]) -> str | None:
    """Return 'fact', 'opinion', or None based on the modules assigned to a need.

    Empty input → None. All-opinion → 'opinion'. Anything else → 'fact'.
    """
    if not assigned_modules:
        return None
    if all(m in _OPINION_MODULES for m in assigned_modules):
        return "opinion"
    return "fact"


async def run_plan_stage(
    triage: TriageOutput,
    disamb: DisambiguationOutput,
    *,
    model: str | None = None,
) -> NeedPlanOutput:
    """LLM Stage 3a: curate the page as a sequence of need sections.

    For each of the 8 reader needs the LLM decides: activation, rank,
    event-specific H2 (`section_title`), rationale, 1–2 Tavily fetch_queries,
    which module kinds belong under it, and a publisher_quota.
    """
    out = await call_structured(
        model=model or get_default_model("plan"),
        messages=build_need_plan_messages(triage, disamb),
        response_model=NeedPlanOutput,
    )
    finalised: list[NeedCurationPlan] = []
    for p in out.need_plans:
        if p.category is None:
            p = p.model_copy(
                update={"category": infer_default_category(p.assigned_modules)}
            )
        finalised.append(p)
    return out.model_copy(update={"need_plans": finalised})


async def run_aesthetic_stage(
    triage: TriageOutput,
    need_plan: NeedPlanOutput,
    evidence_preview: str,
    *,
    model: str | None = None,
) -> AestheticPlanOutput:
    """LLM Stage 3b: pick aesthetic preset + closed-enum overrides."""
    out = await call_structured(
        model=model or get_default_model("aesthetic"),
        messages=build_aesthetic_messages(triage, need_plan, evidence_preview),
        response_model=AestheticPlanOutput,
    )

    if out.preset_confidence < AESTHETIC_CONFIDENCE_THRESHOLD:
        log.warning(
            "Aesthetic preset_confidence %.2f < %.2f; falling back to 'reference'.",
            out.preset_confidence,
            AESTHETIC_CONFIDENCE_THRESHOLD,
        )
        out = out.model_copy(update={"preset_id": "reference"})
    return out
