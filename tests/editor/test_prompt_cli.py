"""Tests for EditorPrompter — all HITL touchpoints."""

from __future__ import annotations

import rich.prompt

from generator.editor.prompt_cli import EditorPrompter
from generator.pipeline.trace import TraceRecorder
from generator.schema import (
    EventFacts,
    GroundOutput,
    NeedCurationPlan,
    NeedPlanOutput,
    TierQuota,
)

_ALL_NEEDS = (
    "what_happened",
    "when_where",
    "who_involved",
    "current_state",
    "why_matters",
    "world_reaction",
    "what_can_do",
    "what_next",
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
    assert any(
        a.reason == "auto_mode" and a.action == "reject_page" for a in actions
    )


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
    assert any(a.action == "accept_module" for a in trace.editor_actions)


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
    assert any(
        a.reason == "manual_reject_not_hot" for a in trace.editor_actions
    )


# ---------------------------------------------------------------------------
# 3. plan_review
# ---------------------------------------------------------------------------


def _plan() -> NeedPlanOutput:
    plans = [
        NeedCurationPlan(
            need_id=nid,
            activated=(idx < 3),
            rank=idx + 1,
            section_title=f"Section {nid}",
            rationale="test",
            fetch_queries=[],
            assigned_modules=["hero"] if idx == 0 else [],
            publisher_quota=TierQuota(),
        )
        for idx, nid in enumerate(_ALL_NEEDS)
    ]
    return NeedPlanOutput(need_plans=plans, layout_preset_id="live_dominance")


def test_plan_review_auto_mode() -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    plan = _plan()
    result = prompter.plan_review(plan)
    assert result is plan
    trace = recorder.finalize(auto_mode=True)
    assert any(a.reason == "auto_mode" for a in trace.editor_actions)


def test_plan_review_interactive_toggles_need(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    plan = _plan()
    # what_happened is activated by default; toggle should deactivate it.
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: "what_happened"),
    )
    result = prompter.plan_review(plan)
    wh = next(p for p in result.need_plans if p.need_id == "what_happened")
    assert wh.activated is False
    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "edit_module_field" for a in trace.editor_actions)


def test_plan_review_interactive_keep(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    plan = _plan()

    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: ""),
    )

    result = prompter.plan_review(plan)
    # No edit made → plan unchanged in content and no editor action logged.
    wh = next(p for p in result.need_plans if p.need_id == "what_happened")
    assert wh.activated is True
    trace = recorder.finalize(auto_mode=False)
    assert trace.editor_actions == []


# ---------------------------------------------------------------------------
# 4. module_review
# ---------------------------------------------------------------------------


def _hero_module():
    """Build a minimal HeroModule via model_construct to avoid heavy validation."""
    from generator.schema import (
        ConfidenceSignals,
        HeroData,
        HeroModule,
        ModuleConfidence,
    )

    conf = ModuleConfidence.model_construct(
        overall=0.6,
        field_level={},
        signals=ConfidenceSignals.model_construct(
            source_count=1,
            publisher_count=1,
            highest_tier="T2",
            schema_passes=True,
            cross_source_agreement=0.7,
        ),
        flags=[],
    )
    data = HeroData.model_construct(
        title="Test Hero",
        subtitle=None,
        summary="A summary.",
        image_url=None,
        image_alt="alt text",
        badge_label=None,
    )
    return HeroModule.model_construct(
        module_id="m1",
        serves_needs=["what_happened"],
        citations=[],
        confidence=conf,
        slot="hero",
        artifact="hero.html",
        artifact_alternatives=[],
        inclusion_reason="required",
        kind="hero",
        data=data,
    )


def test_module_review_auto_mode() -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    module = _hero_module()
    action, result = prompter.module_review(module)
    assert action == "keep"
    assert result is module
    trace = recorder.finalize(auto_mode=True)
    assert any(a.reason == "auto_mode" for a in trace.editor_actions)


def test_module_review_interactive_accept(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    module = _hero_module()

    answers = iter(["a"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    action, result = prompter.module_review(module)
    assert action == "keep"
    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "accept_module" for a in trace.editor_actions)


def test_module_review_interactive_regen(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    module = _hero_module()

    answers = iter(["r"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    action, result = prompter.module_review(module)
    assert action == "regen"
    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "regenerate_module" for a in trace.editor_actions)


def test_module_review_interactive_skip(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    module = _hero_module()

    answers = iter(["s"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    action, result = prompter.module_review(module)
    assert action == "skip"
    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "skip_module" for a in trace.editor_actions)


def test_module_review_interactive_view_then_accept(monkeypatch) -> None:
    """v → prints confidence, loops; a → accept. No log for v, one log for a."""
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    module = _hero_module()

    answers = iter(["v", "a"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    action, result = prompter.module_review(module)
    assert action == "keep"

    trace = recorder.finalize(auto_mode=False)
    # Only one log entry (accept); view sources is not logged
    assert len(trace.editor_actions) == 1
    assert trace.editor_actions[0].action == "accept_module"


# ---------------------------------------------------------------------------
# 5. final_approval
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


def test_final_approval_interactive_regen_module(monkeypatch, tmp_path) -> None:
    html_file = tmp_path / "page.html"
    html_file.write_text("<html></html>")

    monkeypatch.setattr("webbrowser.open", lambda *a, **k: None)
    answers = iter(["r hero"])
    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: next(answers)),
    )

    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    result = prompter.final_approval(html_file)
    assert result == ("regen", "hero")

    trace = recorder.finalize(auto_mode=False)
    assert any(
        a.action == "regenerate_module"
        and getattr(a.target, "module_kind", None) == "hero"
        for a in trace.editor_actions
    )


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
