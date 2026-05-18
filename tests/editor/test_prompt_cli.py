"""Tests for EditorPrompter — all HITL touchpoints."""

from __future__ import annotations

import asyncio

import rich.prompt

from generator.editor.prompt_cli import EditorPrompter
from generator.pipeline.trace import TraceRecorder
from generator.schema import (
    AcceptanceCriteria,
    EventFacts,
    GroundOutput,
    SectionPlan,
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


# ---------------------------------------------------------------------------
# 2. plan_review — multi-select + comments + add-section
# ---------------------------------------------------------------------------


def _plan(section_id: str, *, kind="curated", rank=5, block_kind="paragraph"):
    return SectionPlan(
        section_id=section_id,
        kind=kind,
        title=f"Title {section_id}",
        rank=rank,
        block_kind=block_kind,
        intent=f"intent for {section_id}",
        acceptance=AcceptanceCriteria(description="ok"),
    )


def _facts():
    return EventFacts(
        entities=["X"],
        what="something happened",
        when="2026-05-14T00:00:00+00:00",
        supporting_sources=["s1"],
    )


class _StubAsk:
    """Stand-in for a questionary prompt object — both sync .ask() and .ask_async()."""

    def __init__(self, value):
        self._value = value

    def ask(self):
        return self._value

    async def ask_async(self):
        return self._value


def _patch_questionary(monkeypatch, *, selects, checkboxes, texts, confirms):
    """Queue answers for each questionary function used by plan_review."""
    sel_iter = iter(selects)
    chk_iter = iter(checkboxes)
    txt_iter = iter(texts)
    cnf_iter = iter(confirms)
    monkeypatch.setattr("questionary.select", lambda *a, **k: _StubAsk(next(sel_iter)))
    monkeypatch.setattr(
        "questionary.checkbox", lambda *a, **k: _StubAsk(next(chk_iter))
    )
    monkeypatch.setattr("questionary.text", lambda *a, **k: _StubAsk(next(txt_iter)))
    monkeypatch.setattr("questionary.confirm", lambda *a, **k: _StubAsk(next(cnf_iter)))


def test_plan_review_auto_mode_returns_empty_notes() -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    backbone = [_plan("overview", kind="backbone", rank=1)]
    curated = [_plan("kpi_dashboard", rank=5)]
    decision, sections, notes = asyncio.run(
        prompter.plan_review(
            backbone=backbone, curated=curated, facts=_facts(), canonical_title="t"
        )
    )
    assert decision == "accept"
    assert [s.section_id for s in sections] == ["kpi_dashboard"]
    assert notes.section_comments == {}
    assert notes.global_comment is None


def test_plan_review_reject(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    _patch_questionary(
        monkeypatch,
        selects=["Reject plan"],
        checkboxes=[],
        texts=[],
        confirms=[],
    )
    decision, sections, notes = asyncio.run(
        prompter.plan_review(
            backbone=[_plan("overview", kind="backbone", rank=1)],
            curated=[_plan("kpi_dashboard", rank=5)],
            facts=_facts(),
            canonical_title="t",
        )
    )
    assert decision == "reject"
    assert sections == []
    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "reject_page" for a in trace.editor_actions)


def test_plan_review_drop_comment_and_global_note(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)

    # selects: top-menu, per-section action for "overview", per-section action for
    # "kpi_dashboard", top-menu again.
    selects = [
        "Comment / drop sections",
        "Add / replace comment",  # for overview (backbone)
        "Drop section",  # for kpi_dashboard
        "Accept all as-is",
    ]
    # one checkbox: pick both sections
    checkboxes = [["overview", "kpi_dashboard"]]
    # texts: one section comment, one global comment
    texts = ["Make it punchier.", "Be concise overall."]
    confirms: list = []
    _patch_questionary(
        monkeypatch,
        selects=selects,
        checkboxes=checkboxes,
        texts=texts,
        confirms=confirms,
    )

    backbone = [_plan("overview", kind="backbone", rank=1)]
    curated = [_plan("kpi_dashboard", rank=5)]
    decision, sections, notes = asyncio.run(
        prompter.plan_review(
            backbone=backbone,
            curated=curated,
            facts=_facts(),
            canonical_title="t",
        )
    )
    assert decision == "accept"
    assert [s.section_id for s in sections] == []  # kpi_dashboard dropped
    assert notes.section_comments == {"overview": "Make it punchier."}
    assert notes.global_comment == "Be concise overall."
    actions = recorder.finalize(auto_mode=False).editor_actions
    assert any(
        a.action == "comment_section" and a.target and a.target.section_id == "overview"
        for a in actions
    )
    assert any(a.action == "skip_section" for a in actions)
    assert any(
        a.action == "comment_section"
        and (a.target is None or a.target.section_id is None)
        for a in actions
    )
    assert any(a.action == "accept_section" for a in actions)


def test_plan_review_add_section(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)

    new_plan = _plan("sponsor_reactions", rank=6, block_kind="reactions")

    async def fake_propose(description, *, facts, canonical_title, existing_sections):
        assert description == "I want sponsor reactions"
        return new_plan

    monkeypatch.setattr(
        "generator.pipeline.section_proposer.propose_section", fake_propose
    )

    selects = ["Add a new section", "Accept all as-is"]
    checkboxes: list = []
    texts = ["I want sponsor reactions", ""]  # description, then blank global
    confirms = [True]
    _patch_questionary(
        monkeypatch,
        selects=selects,
        checkboxes=checkboxes,
        texts=texts,
        confirms=confirms,
    )

    backbone = [_plan("overview", kind="backbone", rank=1)]
    curated = [_plan("kpi_dashboard", rank=5)]
    decision, sections, notes = asyncio.run(
        prompter.plan_review(
            backbone=backbone,
            curated=curated,
            facts=_facts(),
            canonical_title="t",
        )
    )
    assert decision == "accept"
    assert [s.section_id for s in sections] == ["kpi_dashboard", "sponsor_reactions"]
    assert notes.global_comment is None
    actions = recorder.finalize(auto_mode=False).editor_actions
    assert any(a.action == "add_section" for a in actions)


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
