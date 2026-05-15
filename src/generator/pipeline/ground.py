"""Stage 1 — Ground.

Replaces the previous triage + disambiguate stages. A single LLM call sees
the input sentence alongside fresh Tavily evidence and produces a
GroundOutput that either (a) gates the pipeline because the input is not
an unfolding hot event, or (b) carries grounded EventFacts forward.
"""

from __future__ import annotations

from generator.llm.client import call_structured, get_default_model
from generator.prompts.ground import build_ground_messages
from generator.schema import GroundOutput
from generator.sources.tavily import fetch_tavily

# 14-day window is itself a first-pass freshness filter: evergreen queries
# typically return zero or only undated reference content here.
_TIME_RANGE_DAYS = 14
_MAX_RESULTS = 8


async def run(input_sentence: str, *, model: str | None = None) -> GroundOutput:
    """Run the ground stage.

    Tavily evidence is used to ground the LLM's judgment + fact extraction
    but is not propagated downstream — Stage 3 (fetch) runs its own
    plan-driven queries with full publisher-quota logic.
    """
    evidence = await fetch_tavily(
        input_sentence,
        time_range_days=_TIME_RANGE_DAYS,
        max_results=_MAX_RESULTS,
    )
    return await call_structured(
        model=model or get_default_model("ground"),
        messages=build_ground_messages(input_sentence, evidence),
        response_model=GroundOutput,
    )
