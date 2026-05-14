"""Stage 2 — Disambiguation. Conditionally fires Tavily + LLM."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from generator.llm.client import call_structured, get_default_model
from generator.prompts.disambiguate import build_disambiguate_messages
from generator.schema import (
    DisambiguationChosen,
    DisambiguationOutput,
    TriageOutput,
)
from generator.sources.tavily import fetch_tavily

log = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.85


def _short_circuit(triage: TriageOutput) -> DisambiguationOutput:
    """Build a DisambiguationOutput from a confident triage without LLM/search."""
    return DisambiguationOutput(
        resolved=True,
        chosen=DisambiguationChosen(
            entity=triage.primary_entity or "Unknown",
            event_type_hint=triage.event_type_hint or "generic_event",
            time_anchor=triage.time_anchor or datetime.now(timezone.utc).isoformat(),
            supporting_sources=[],  # no evidence pulled at this stage
        ),
        unresolved_candidates=[],
    )


async def run(
    triage: TriageOutput, *, model: str | None = None
) -> DisambiguationOutput:
    if triage.confidence >= CONFIDENCE_THRESHOLD:
        return _short_circuit(triage)

    # Build a search query from triage alternatives.
    candidates = [a.entity for a in triage.alternatives] or [
        triage.primary_entity or ""
    ]
    query = " OR ".join(f'"{c}"' for c in candidates if c)
    evidence = await fetch_tavily(
        query, time_range_days=30, max_results=8, primary_entity=triage.primary_entity
    )

    if not evidence:
        log.warning(
            "Disambiguate found no evidence for ambiguous triage; falling back to top triage candidate."
        )
        return _short_circuit(triage)

    return await call_structured(
        model=model or get_default_model("disambiguate"),
        messages=build_disambiguate_messages(triage, evidence),
        response_model=DisambiguationOutput,
    )
