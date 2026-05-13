"""Stage 1 — Triage. Stub returns high-confidence classification."""
from __future__ import annotations

from generator.schema import TriageOutput


def run(input_sentence: str) -> TriageOutput:
    return TriageOutput(
        is_event=True,
        primary_entity="GPT-5.5 Instant",
        event_type_hint="product_launch",
        temporal_posture="recent",
        time_anchor="2026-05-01T00:00:00Z",
        confidence=0.92,
        alternatives=[],
        reasoning="stub: high-confidence product_launch from input sentence",
    )
