"""Stage 1 — Triage. Stub returns high-confidence classification."""
from __future__ import annotations

from generator.schema import TriageOutput


def run(input_sentence: str) -> TriageOutput:
    return TriageOutput(
        is_event=True,
        # Include the responsible org so tier_for's T0 substring match resolves
        # openai.com → T0 for this event. PR 3 (real LLM triage) will naturally
        # surface the maker in primary_entity; until then, the stub does it explicitly.
        primary_entity="GPT-5.5 Instant (OpenAI)",
        event_type_hint="product_launch",
        temporal_posture="recent",
        time_anchor="2026-05-01T00:00:00Z",
        confidence=0.92,
        alternatives=[],
        reasoning="stub: high-confidence product_launch from input sentence",
    )
