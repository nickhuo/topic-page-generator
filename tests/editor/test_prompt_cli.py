"""Tests for EditorPrompter — all HITL touchpoints."""

from __future__ import annotations

import rich.prompt

from generator.editor.prompt_cli import EditorPrompter
from generator.pipeline.trace import TraceRecorder
from generator.schema import (
    EventFacts,
    GroundOutput,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _recorder() -> TraceRecorder:
    return TraceRecorder(input_sentence="test sentence", page_id="page_test")


def _prompter(auto_mode: bool, recorder: TraceRecorder | None = None) -> EditorPrompter:
    from rich.console import Console

    rec = recorder or _recorder()
    return EditorPrompter(
        auto_mode=auto_mode, recorder=rec, console=Console(quiet=True)
    )


def _ground_hot() -> GroundOutput:
    return GroundOutput(
        is_hot_event=True,
        rejection_reason=None,
        facts=EventFacts(
            entities=["Test Event"],
            what="Test event happened.",
            when="2026-05-14T00:00:00+00:00",
            supporting_sources=["s1"],
        ),
        canonical_title="Test Event",
        confidence=0.92,
        reasoning="fresh evidence",
    )


def _ground_not_hot() -> GroundOutput:
    return GroundOutput(
        is_hot_event=False,
        rejection_reason="Query reads as evergreen tutorial.",
        facts=None,
        canonical_title=None,
        confidence=0.95,
        reasoning="no time-bound event in evidence",
    )


# ---------------------------------------------------------------------------
# 1. ground_review
# ---------------------------------------------------------------------------


def test_ground_review_auto_mode_accepts_hot_event() -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    out = _ground_hot()
    decision, payload = prompter.ground_review(out)
    assert decision == "accept"
    assert payload is out
    trace = recorder.finalize(auto_mode=True)
    assert any(a.reason == "auto_mode" for a in trace.editor_actions)


def test_ground_review_auto_mode_rejects_non_hot() -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    out = _ground_not_hot()
    decision, payload = prompter.ground_review(out)
    assert decision == "reject"
    assert payload is out
    trace = recorder.finalize(auto_mode=True)
    actions = trace.editor_actions
    assert any(a.reason == "auto_mode" and a.action == "reject_page" for a in actions)


def test_ground_review_interactive_accepts_facts(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    out = _ground_hot()

    answers = iter(["y"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    decision, payload = prompter.ground_review(out)
    assert decision == "accept"
    assert payload.facts == out.facts
    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "accept_section" for a in trace.editor_actions)


def test_ground_review_interactive_reject_facts(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    out = _ground_hot()

    answers = iter(["n"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    decision, _ = prompter.ground_review(out)
    assert decision == "reject"
    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "reject_page" for a in trace.editor_actions)


def test_ground_review_interactive_reformulate(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    out = _ground_not_hot()

    answers = iter(["r", "Trump visits China"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    decision, payload = prompter.ground_review(out)
    assert decision == "retry"
    assert payload == "Trump visits China"
    trace = recorder.finalize(auto_mode=False)
    assert any(a.reason == "manual_reformulate" for a in trace.editor_actions)


def test_ground_review_interactive_quit_on_not_hot(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    out = _ground_not_hot()

    answers = iter(["q"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    decision, _ = prompter.ground_review(out)
    assert decision == "reject"
    trace = recorder.finalize(auto_mode=False)
    assert any(a.reason == "manual_reject_not_hot" for a in trace.editor_actions)


# ---------------------------------------------------------------------------
# 3. final_approval
# ---------------------------------------------------------------------------


def test_final_approval_auto_mode(tmp_path) -> None:
    html_file = tmp_path / "page.html"
    html_file.write_text("<html></html>")

    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    result = prompter.final_approval(html_file)

    assert result == "approve"
    trace = recorder.finalize(auto_mode=True)
    assert any(
        a.action == "approve_page" and a.reason == "auto_mode"
        for a in trace.editor_actions
    )


def test_final_approval_interactive_approve(monkeypatch, tmp_path) -> None:
    html_file = tmp_path / "page.html"
    html_file.write_text("<html></html>")

    monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
    answers = iter(["y"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    result = prompter.final_approval(html_file)
    assert result == "approve"

    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "approve_page" for a in trace.editor_actions)


def test_final_approval_interactive_reject(monkeypatch, tmp_path) -> None:
    html_file = tmp_path / "page.html"
    html_file.write_text("<html></html>")

    monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
    answers = iter(["n"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    result = prompter.final_approval(html_file)
    assert result == "reject"

    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "reject_page" for a in trace.editor_actions)


def test_final_approval_interactive_invalid_then_approve(monkeypatch, tmp_path) -> None:
    """Invalid input re-prompts; then y approves."""
    html_file = tmp_path / "page.html"
    html_file.write_text("<html></html>")

    monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
    answers = iter(["bad", "y"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    result = prompter.final_approval(html_file)
    assert result == "approve"
