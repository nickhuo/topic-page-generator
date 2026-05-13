"""Stage 2 — Disambiguation. Stub auto-resolves (triage was confident)."""
from __future__ import annotations

from generator.schema import DisambiguationChosen, DisambiguationOutput, TriageOutput


def run(triage: TriageOutput) -> DisambiguationOutput:
    return DisambiguationOutput(
        resolved=True,
        chosen=DisambiguationChosen(
            entity=triage.primary_entity or "Unknown",
            event_type_hint=triage.event_type_hint or "generic",
            time_anchor=triage.time_anchor or "2026-05-01T00:00:00Z",
            supporting_sources=["src_001"],
        ),
        unresolved_candidates=[],
    )
