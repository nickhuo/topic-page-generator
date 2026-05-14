"""Tests for EditorPrompter auto-mode short-circuit."""

from __future__ import annotations

from generator.pipeline.trace import TraceRecorder
from generator.schema import TriageOutput

# Use model_construct to bypass validation — auto-mode never inspects triage internals.
_TRIAGE_LOW = TriageOutput.model_construct(
    is_event=True,
    confidence=0.5,
    reasoning="low confidence stub",
    alternatives=[
        {"entity": "X", "event_type_hint": "launch", "rationale": "alt"},
    ],
)

_TRIAGE_HIGH = TriageOutput.model_construct(
    is_event=True,
    confidence=0.9,
    reasoning="high confidence stub",
    alternatives=[],
)


def _recorder() -> TraceRecorder:
    return TraceRecorder(input_sentence="test sentence", page_id="page_test")


def test_auto_mode_logs_low_confidence_triage() -> None:
    recorder = _recorder()
    from generator.editor.prompt_cli import EditorPrompter

    prompter = EditorPrompter(auto_mode=True, recorder=recorder)
    result = prompter.triage_review(_TRIAGE_LOW, confidence=0.5)

    # auto-mode must return the same object unchanged
    assert result is _TRIAGE_LOW

    trace = recorder.finalize(auto_mode=True)
    reasons = [a.reason for a in trace.editor_actions]
    assert "auto_mode" in reasons, f"Expected 'auto_mode' reason, got: {reasons}"


def test_high_confidence_triage_no_op() -> None:
    recorder = _recorder()
    from generator.editor.prompt_cli import EditorPrompter

    prompter = EditorPrompter(auto_mode=True, recorder=recorder)
    result = prompter.triage_review(_TRIAGE_HIGH, confidence=0.9)

    # high-confidence must return unchanged with no editor actions recorded
    assert result is _TRIAGE_HIGH

    trace = recorder.finalize(auto_mode=True)
    assert trace.editor_actions == [], (
        f"Expected no editor actions for high-confidence, got: {trace.editor_actions}"
    )
