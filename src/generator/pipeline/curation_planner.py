"""Curation planner — one LLM call producing 0-4 curated SectionPlans.

Stage name: "curation". Model fallback: anthropic/claude-sonnet-4-6
(override via MODEL_CURATION env var).

The LLM is constrained to a SectionPlanOutput schema with `kind="curated"`
on every entry. Validation enforces this contract; bad output raises
LLMOutputError which the CLI maps to exit code 4.
"""

from __future__ import annotations

from generator.llm.client import call_structured, get_default_model
from generator.prompts.curation import build_curation_messages
from generator.schema import EventFacts, SectionPlan, SectionPlanOutput


async def run_curation_stage(
    facts: EventFacts,
    canonical_title: str,
    backbone: list[SectionPlan],
    *,
    model: str | None = None,
) -> SectionPlanOutput:
    """One LLM call. Returns 0-4 curated sections to complement the backbone.

    Backbone sections must NOT appear in the output. Caller is responsible
    for combining `backbone + curation_output.sections` before downstream
    stages consume them.
    """
    resolved_model = model or get_default_model("curation")
    messages = build_curation_messages(
        facts=facts, canonical_title=canonical_title, backbone=backbone
    )
    raw = await call_structured(
        model=resolved_model,
        messages=messages,
        response_model=SectionPlanOutput,
    )
    # Hard contract: curated sections always render in the main column.
    # The sidebar is reserved for the backbone timeline (and chrome cards).
    return SectionPlanOutput(
        sections=[s.model_copy(update={"placement": "main"}) for s in raw.sections]
    )


__all__ = ["run_curation_stage"]
