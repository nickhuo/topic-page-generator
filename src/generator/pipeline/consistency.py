"""Stage 6 — Consistency check. Stub always passes."""
from __future__ import annotations

from generator.schema import ConsistencyCheckOutput, TypedModule


def run(_modules: list[TypedModule]) -> ConsistencyCheckOutput:
    return ConsistencyCheckOutput(passes=True, issues=[])
