"""Tests for EditorPrompter — all five HITL touchpoints."""

from __future__ import annotations

import rich.prompt

from generator.editor.prompt_cli import EditorPrompter
from generator.pipeline.trace import TraceRecorder
from generator.schema import (
    DisambiguationCandidate,
    DisambiguationOutput,
    PlanComposition,
    PlanOutput,
    SourceStrategy,
    TriageAlternative,
    TriageOutput,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

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


def _prompter(auto_mode: bool, recorder: TraceRecorder | None = None) -> EditorPrompter:
    from rich.console import Console

    rec = recorder or _recorder()
    return EditorPrompter(
        auto_mode=auto_mode, recorder=rec, console=Console(quiet=True)
    )


# ---------------------------------------------------------------------------
# 1. triage_review — existing tests (Task 2)
# ---------------------------------------------------------------------------


def test_auto_mode_logs_low_confidence_triage() -> None:
    recorder = _recorder()
    prompter = EditorPrompter(auto_mode=True, recorder=recorder)
    result = prompter.triage_review(_TRIAGE_LOW, confidence=0.5)

    assert result is _TRIAGE_LOW
    trace = recorder.finalize(auto_mode=True)
    reasons = [a.reason for a in trace.editor_actions]
    assert "auto_mode" in reasons, f"Expected 'auto_mode' reason, got: {reasons}"


def test_high_confidence_triage_no_op() -> None:
    recorder = _recorder()
    prompter = EditorPrompter(auto_mode=True, recorder=recorder)
    result = prompter.triage_review(_TRIAGE_HIGH, confidence=0.9)

    assert result is _TRIAGE_HIGH
    trace = recorder.finalize(auto_mode=True)
    assert trace.editor_actions == [], (
        f"Expected no editor actions for high-confidence, got: {trace.editor_actions}"
    )


def test_triage_review_interactive_pick_alternative(monkeypatch) -> None:
    """Pick alternative 1 — mutates primary_entity, logs override_archetype."""
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)

    triage = TriageOutput(
        is_event=True,
        primary_entity="OldEntity",
        event_type_hint="conference",
        temporal_posture="imminent",
        confidence=0.5,
        reasoning="test",
        alternatives=[
            TriageAlternative(
                entity="NewEntity",
                event_type_hint="summit",
                rationale="better match",
            )
        ],
    )

    monkeypatch.setattr(
        rich.prompt.IntPrompt,
        "ask",
        staticmethod(lambda *a, **k: 1),
    )

    result = prompter.triage_review(triage, confidence=0.5)
    assert result.primary_entity == "NewEntity"

    trace = recorder.finalize(auto_mode=False)
    actions = trace.editor_actions
    assert len(actions) == 1
    assert actions[0].action == "override_archetype"
    assert actions[0].reason == "low_confidence_pick"
    assert actions[0].before == "OldEntity"
    assert actions[0].after == "NewEntity"


def test_triage_review_interactive_keep_current(monkeypatch) -> None:
    """Pick 0 — keeps current, no log."""
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)

    triage = TriageOutput(
        is_event=True,
        primary_entity="OriginalEntity",
        event_type_hint="conference",
        temporal_posture="imminent",
        confidence=0.5,
        reasoning="test",
        alternatives=[
            TriageAlternative(entity="Alt", event_type_hint="x", rationale="r")
        ],
    )

    monkeypatch.setattr(
        rich.prompt.IntPrompt,
        "ask",
        staticmethod(lambda *a, **k: 0),
    )

    result = prompter.triage_review(triage, confidence=0.5)
    assert result.primary_entity == "OriginalEntity"

    trace = recorder.finalize(auto_mode=False)
    assert trace.editor_actions == []


# ---------------------------------------------------------------------------
# 2. disambiguation_review
# ---------------------------------------------------------------------------


def _disamb_unresolved() -> DisambiguationOutput:
    return DisambiguationOutput(
        resolved=False,
        chosen=None,
        unresolved_candidates=[
            DisambiguationCandidate(
                entity="EntityA",
                event_type_hint="summit",
                rationale="reason A",
                supporting_sources=["s1"],
            ),
            DisambiguationCandidate(
                entity="EntityB",
                event_type_hint="conference",
                rationale="reason B",
                supporting_sources=["s2"],
            ),
        ],
    )


def test_disambiguation_review_auto_mode() -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    disamb = _disamb_unresolved()
    result = prompter.disambiguation_review(disamb)
    assert result is disamb
    trace = recorder.finalize(auto_mode=True)
    assert any(a.reason == "auto_mode" for a in trace.editor_actions)


def test_disambiguation_review_interactive_pick(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    disamb = _disamb_unresolved()

    monkeypatch.setattr(
        rich.prompt.IntPrompt,
        "ask",
        staticmethod(lambda *a, **k: 1),
    )

    result = prompter.disambiguation_review(disamb)
    assert result.resolved is True
    assert result.chosen is not None
    assert result.chosen.entity == "EntityA"

    trace = recorder.finalize(auto_mode=False)
    assert any(a.reason == "manual_disambiguation" for a in trace.editor_actions)


# ---------------------------------------------------------------------------
# 3. plan_review
# ---------------------------------------------------------------------------


def _plan() -> PlanOutput:
    return PlanOutput(
        archetype_hint="live_event",
        layout_preset_id="live_dominance",
        composition=[
            PlanComposition(
                module_kind="hero",
                artifact="hero.html",
                slot="hero",
                priority="required",
            )
        ],
        source_strategy=SourceStrategy(
            preferred_tiers=["T0", "T1"],
            time_range_days=7,
            min_publishers=3,
        ),
    )


def test_plan_review_auto_mode() -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=True, recorder=recorder)
    plan = _plan()
    result = prompter.plan_review(plan)
    assert result is plan
    trace = recorder.finalize(auto_mode=True)
    assert any(a.reason == "auto_mode" for a in trace.editor_actions)


def test_plan_review_interactive_override(monkeypatch) -> None:
    recorder = _recorder()
    prompter = _prompter(auto_mode=False, recorder=recorder)
    plan = _plan()

    monkeypatch.setattr(
        rich.prompt.Prompt,
        "ask",
        staticmethod(lambda *a, **k: "product_focus"),
    )

    result = prompter.plan_review(plan)
    assert result.archetype_hint == "product_focus"

    trace = recorder.finalize(auto_mode=False)
    assert any(a.action == "override_archetype" for a in trace.editor_actions)


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
    assert result.archetype_hint == "live_event"
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
