"""Research-eval stage — one LLM call per loop iteration.

The LLM acts as a judge over the current evidence pool for a single section.
"""

from __future__ import annotations

from generator.llm.client import call_structured, get_default_model
from generator.prompts.research_eval import build_research_eval_messages
from generator.schema import ResearchEvalResult, SectionPlan, Source


async def run_research_eval_stage(
    *,
    section: SectionPlan,
    sources: list[Source],
    canonical_title: str,
    model: str | None = None,
) -> ResearchEvalResult:
    resolved_model = model or get_default_model("research_eval")
    messages = build_research_eval_messages(
        section=section, sources=sources, canonical_title=canonical_title
    )
    return await call_structured(
        model=resolved_model,
        messages=messages,
        response_model=ResearchEvalResult,
    )


__all__ = ["run_research_eval_stage"]
