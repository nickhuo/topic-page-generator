"""Stage 1 — Triage. Single LLM call → TriageOutput."""

from __future__ import annotations

from generator.llm.client import call_structured, get_default_model
from generator.prompts.triage import build_triage_messages
from generator.schema import TriageOutput


async def run(input_sentence: str, *, model: str | None = None) -> TriageOutput:
    return await call_structured(
        model=model or get_default_model("triage"),
        messages=build_triage_messages(input_sentence),
        response_model=TriageOutput,
    )
