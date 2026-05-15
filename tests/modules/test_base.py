"""Tests for Module ABC + PlanContext + MODULE_REGISTRY."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ValidationError

from generator.modules import MODULE_REGISTRY
from generator.modules.base import Module, PlanContext, compute_default_confidence
from generator.schema import (
    AestheticOverrides,
    AestheticPlanOutput,
    EventSubject,
    NeedCurationPlan,
    NeedPlanOutput,
    Publisher,
    Source,
    SourceRights,
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


def test_module_registry_is_a_dict():
    assert isinstance(MODULE_REGISTRY, dict)


def test_module_abc_cannot_instantiate():
    with pytest.raises(TypeError):
        Module()  # type: ignore[abstract]


def _make_ctx() -> PlanContext:
    subject = EventSubject(
        title="GPT-5.5 Instant rollout",
        entities=["GPT-5.5 Instant (OpenAI)"],
    )
    need_plans = [
        NeedCurationPlan(
            need_id=nid,
            activated=(idx == 0),
            rank=idx + 1,
            section_title=f"Section {nid}",
            rationale="ok",
            fetch_queries=[],
            assigned_modules=["hero"] if idx == 0 else [],
            publisher_quota=TierQuota(),
        )
        for idx, nid in enumerate(_ALL_NEEDS)
    ]
    need_plan = NeedPlanOutput(need_plans=need_plans, layout_preset_id="product_focus")
    aesthetic = AestheticPlanOutput(
        preset_id="product_focus",
        preset_confidence=0.9,
        alternatives_considered=[],
        aesthetic_overrides=AestheticOverrides(),
        reasoning="ok",
    )
    return PlanContext(subject=subject, need_plan=need_plan, aesthetic=aesthetic)


def test_plan_context_is_frozen():
    ctx = _make_ctx()
    with pytest.raises(ValidationError):
        ctx.subject = None  # type: ignore[misc]


def test_subclass_auto_registers_into_registry():
    class _StubData(BaseModel):
        x: int

    class _StubModule(Module):
        kind = "_stub"
        serves_needs = ["what_happened"]
        allowed_artifacts = ["Stub"]
        data_schema = _StubData
        extraction_prompt_template = "irrelevant"

        def queries(self, ctx):
            return ["q"]

        def should_render(self, data):
            return True

    try:
        assert MODULE_REGISTRY.get("_stub") is _StubModule
    finally:
        MODULE_REGISTRY.pop("_stub", None)


def test_default_artifact_returns_first_allowed():
    class _StubData(BaseModel):
        x: int = 1

    class _Mystery(Module):
        kind = "mystery"
        serves_needs = ["what_happened"]
        allowed_artifacts = ["A", "B"]
        data_schema = _StubData
        extraction_prompt_template = "irrelevant"

        def queries(self, ctx):
            return []

        def should_render(self, data):
            return True

    try:
        ctx = _make_ctx()
        assert _Mystery().default_artifact(ctx, _StubData()) == "A"
    finally:
        MODULE_REGISTRY.pop("mystery", None)


def _src(name: str, tier: str) -> Source:
    return Source(
        id=f"src_{name}",
        url=f"https://{name}.example/x",
        publisher=Publisher(name=name, tier=tier),
        title="t",
        published_at="2026-05-01T00:00:00+00:00",
        fetched_at="2026-05-01T00:00:00+00:00",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )


def test_compute_default_confidence_flags_single_source():
    class D(BaseModel): ...

    conf = compute_default_confidence([_src("openai", "T0")], D())
    assert "single_source" in conf.flags
    assert "low_tier_only" not in conf.flags


def test_compute_default_confidence_flags_low_tier_only():
    class D(BaseModel): ...

    conf = compute_default_confidence([_src("blog1", "T3"), _src("blog2", "T3")], D())
    assert "low_tier_only" in conf.flags
    assert "single_source" not in conf.flags


def test_compute_default_confidence_flags_contested():
    class D(BaseModel): ...

    conf = compute_default_confidence(
        [_src("nyt", "T1"), _src("verge", "T1")],
        D(),
        contested_fields=["date"],
    )
    assert "contested_fact" in conf.flags
    assert conf.signals.cross_source_agreement < 1.0
