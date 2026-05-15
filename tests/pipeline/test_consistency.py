"""Tests for Stage 6 — consistency check + needs_coverage."""

from __future__ import annotations

import json
from datetime import datetime, timezone

import httpx
import pytest
import respx

from generator.llm.trace_buffer import reset
from generator.modules.base import PlanContext
from generator.pipeline.consistency import (
    _compute_needs_coverage,
    _flag_reactions_sentiment,
    run,
)
from generator.schema import (
    AestheticOverrides,
    AestheticPlanOutput,
    ChangelogData,
    ChangelogEntry,
    ChangelogModule,
    ConfidenceSignals,
    EventSubject,
    HeroData,
    HeroModule,
    InfoboxData,
    InfoboxModule,
    InfoboxRow,
    ModuleConfidence,
    NeedCurationPlan,
    NeedPlanOutput,
    Publisher,
    ReactionItem,
    ReactionsData,
    ReactionsModule,
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


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _make_source(sid: str = "src_1") -> Source:
    return Source(
        id=sid,
        url="https://example.com/article",
        publisher=Publisher(name="TechCrunch", tier="T0"),
        title=f"Article {sid}",
        published_at=datetime.now(timezone.utc).isoformat(),
        fetched_at=datetime.now(timezone.utc).isoformat(),
        language="en",
        rights=SourceRights(max_excerpt_words=100, can_paraphrase=True),
    )


def _make_confidence() -> ModuleConfidence:
    return ModuleConfidence(
        overall=0.9,
        signals=ConfidenceSignals(
            source_count=1,
            publisher_count=1,
            highest_tier="T0",
            schema_passes=True,
            cross_source_agreement=1.0,
        ),
    )


def _make_plan(module_kinds: list[str] | None = None) -> NeedPlanOutput:
    if module_kinds is None:
        module_kinds = ["hero", "infobox"]
    plans = []
    for idx, nid in enumerate(_ALL_NEEDS):
        plans.append(
            NeedCurationPlan(
                need_id=nid,
                activated=(idx == 0),
                rank=idx + 1,
                section_title=f"Section {nid}",
                rationale="test",
                fetch_queries=[],
                assigned_modules=module_kinds if idx == 0 else [],
                publisher_quota=TierQuota(),
            )
        )
    return NeedPlanOutput(need_plans=plans, layout_preset_id="product_focus")


def _make_aesthetic() -> AestheticPlanOutput:
    return AestheticPlanOutput(
        preset_id="product_focus",
        preset_confidence=0.9,
        aesthetic_overrides=AestheticOverrides(),
        reasoning="test",
    )


def _make_subject() -> EventSubject:
    return EventSubject(
        title="GPT-5.5 Instant rollout",
        entities=["GPT-5.5 Instant (OpenAI)"],
    )


def _make_ctx() -> PlanContext:
    return PlanContext(
        subject=_make_subject(),
        need_plan=_make_plan(["hero", "changelog"]),
        aesthetic=_make_aesthetic(),
    )


def _make_hero_module() -> HeroModule:
    return HeroModule.model_construct(
        kind="hero",
        module_id="mod_hero",
        serves_needs=["what_happened"],
        citations=[],
        confidence=_make_confidence(),
        slot="hero",
        artifact="HeroBanner",
        artifact_alternatives=[],
        inclusion_reason="required",
        data=HeroData(
            title="GPT-5.5 Instant is Now Default",
            subtitle=None,
            summary="OpenAI set GPT-5.5 Instant as the default ChatGPT model.",
            image_url=None,
            image_alt="OpenAI logo",
            badge_label="PRODUCT LAUNCH",
        ),
    )


def _make_infobox_module() -> InfoboxModule:
    return InfoboxModule.model_construct(
        kind="infobox",
        module_id="mod_infobox",
        serves_needs=["what_happened", "who_involved"],
        citations=[],
        confidence=_make_confidence(),
        slot="aside",
        artifact="Infobox",
        artifact_alternatives=[],
        inclusion_reason="required",
        data=InfoboxData(
            rows=[
                InfoboxRow(label="Vendor", value="OpenAI", source_id="src_1"),
                InfoboxRow(label="Release", value="May 2026", source_id="src_1"),
                InfoboxRow(label="Replaces", value="GPT-5.3", source_id="src_1"),
                InfoboxRow(label="Surface", value="ChatGPT default", source_id="src_1"),
                InfoboxRow(label="Pricing", value="Same tiers", source_id="src_1"),
            ]
        ),
    )


def _make_changelog_module() -> ChangelogModule:
    return ChangelogModule.model_construct(
        kind="changelog",
        module_id="mod_changelog",
        serves_needs=["what_next"],
        citations=[],
        confidence=_make_confidence(),
        slot="primary",
        artifact="Changelog",
        artifact_alternatives=[],
        inclusion_reason="medium",
        data=ChangelogData(
            version_label="5.5",
            entries=[
                ChangelogEntry(
                    label="Default model swap",
                    description="GPT-5.5 Instant replaces GPT-5.3 as the ChatGPT default.",
                    importance="feature",
                    source_id="src_1",
                ),
            ],
        ),
    )


def _openrouter_envelope(content_json: str) -> dict:
    return {
        "id": "gen-test-consistency",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content_json},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 50, "total_tokens": 150},
    }


# ---------------------------------------------------------------------------
# Test 1: passes when no issues
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_consistency_passes_when_no_issues(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    hero = _make_hero_module()
    infobox = _make_infobox_module()

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json=_openrouter_envelope(json.dumps({"passes": True, "issues": []}))
        )
    )

    result, modules_out, needs_coverage, uncovered = await run(
        [hero, infobox], _make_ctx(), []
    )

    assert result.passes is True
    assert result.issues == []
    assert len(modules_out) == 2
    # hero serves what_happened
    assert "mod_hero" in needs_coverage["what_happened"]
    # infobox serves what_happened and who_involved
    assert "mod_infobox" in needs_coverage["what_happened"]
    assert "mod_infobox" in needs_coverage["who_involved"]


# ---------------------------------------------------------------------------
# Test 2: _compute_needs_coverage pure unit test
# ---------------------------------------------------------------------------


def test_compute_needs_coverage_unions_correctly():
    hero = _make_hero_module()  # serves: what_happened
    infobox = _make_infobox_module()  # serves: what_happened, who_involved

    coverage, uncovered = _compute_needs_coverage([hero, infobox])

    assert set(coverage["what_happened"]) == {"mod_hero", "mod_infobox"}
    assert coverage["who_involved"] == ["mod_infobox"]
    # needs not served by any module
    for need in (
        "when_where",
        "current_state",
        "why_matters",
        "world_reaction",
        "what_can_do",
        "what_next",
    ):
        assert need in uncovered
    assert "what_happened" not in uncovered
    assert "who_involved" not in uncovered


# ---------------------------------------------------------------------------
# Test 3: remove action drops module
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_remove_action_drops_module(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    changelog = _make_changelog_module()
    hero = _make_hero_module()

    first_response = json.dumps(
        {
            "passes": False,
            "issues": [
                {
                    "severity": "warning",
                    "module_kind": "changelog",
                    "field_path": "entries",
                    "description": "changelog not relevant for this event",
                    "recommended_action": "remove",
                }
            ],
        }
    )
    second_response = json.dumps({"passes": True, "issues": []})

    call_count = 0

    def side_effect(request):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return httpx.Response(200, json=_openrouter_envelope(first_response))
        return httpx.Response(200, json=_openrouter_envelope(second_response))

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=side_effect
    )

    result, modules_out, needs_coverage, uncovered = await run(
        [changelog, hero], _make_ctx(), []
    )

    kinds_out = {m.kind for m in modules_out}
    assert "changelog" not in kinds_out
    assert "hero" in kinds_out
    assert result.passes is True


# ---------------------------------------------------------------------------
# Test 4: regenerate triggers module rerun, caps at MAX_PAGE_REGENS (2)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_regenerate_triggers_module_rerun_and_caps_at_two(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    hero = _make_hero_module()

    regen_issue_response = json.dumps(
        {
            "passes": False,
            "issues": [
                {
                    "severity": "error",
                    "module_kind": "hero",
                    "field_path": "title",
                    "description": "title contradicts infobox date",
                    "recommended_action": "regenerate",
                }
            ],
        }
    )

    valid_hero_data = json.dumps(
        {
            "title": "GPT-5.5 Instant is Now ChatGPT Default",
            "subtitle": "OpenAI makes the switch in May 2026",
            "summary": "OpenAI set GPT-5.5 Instant as the default model.",
            "image_url": None,
            "image_alt": "OpenAI logo",
            "badge_label": "PRODUCT LAUNCH",
        }
    )

    extract_call_count = 0
    consistency_call_count = 0

    def side_effect(request):
        nonlocal extract_call_count, consistency_call_count
        body = json.loads(request.content)
        # Determine if this is a consistency call (system prompt contains "cross-module conflicts")
        # or an extract call (system prompt is BASE_PREAMBLE only)
        system_content = next(
            (m["content"] for m in body["messages"] if m["role"] == "system"), ""
        )
        if "cross-module conflicts" in system_content:
            consistency_call_count += 1
            # Always return regen issue — consistency never passes
            return httpx.Response(200, json=_openrouter_envelope(regen_issue_response))
        else:
            # This is an extract regen call
            extract_call_count += 1
            return httpx.Response(200, json=_openrouter_envelope(valid_hero_data))

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=side_effect
    )

    # Need evidence pool with src_1 so extract_one_module can succeed citation check
    evidence = [_make_source("src_1")]

    # Use a ctx that includes hero in the need plan so extract_one_module works
    ctx = PlanContext(
        subject=_make_subject(),
        need_plan=_make_plan(["hero"]),
        aesthetic=_make_aesthetic(),
    )

    result, modules_out, _, _ = await run([hero], ctx, evidence)

    # extract was called exactly MAX_PAGE_REGENS (2) times
    assert extract_call_count == 2
    # consistency was called: initial + after each regen = 3 total (initial + 2 regens)
    assert consistency_call_count == 3
    # Result is still failing since regens exhausted without fix
    assert result.passes is False


# ---------------------------------------------------------------------------
# Test 5: LLM failure falls back to passes=True (safety net)
# ---------------------------------------------------------------------------


@respx.mock
@pytest.mark.asyncio
async def test_llm_failure_falls_back_to_passes_true(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    hero = _make_hero_module()

    # Return malformed JSON that will fail both validation attempts
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json=_openrouter_envelope("NOT VALID JSON {{{")
        )
    )

    # Should not raise; should return passes=True via the safety net
    result, modules_out, needs_coverage, uncovered = await run([hero], _make_ctx(), [])

    assert result.passes is True
    assert result.issues == []
    # Modules are returned unchanged
    assert len(modules_out) == 1
    assert modules_out[0].kind == "hero"


# ---------------------------------------------------------------------------
# Sentiment-coverage flag for reactions
# ---------------------------------------------------------------------------


def _make_reactions_module(sentiments: list[str]) -> ReactionsModule:
    items = [
        ReactionItem(
            author=f"Author {i}",
            author_role="Analyst",
            quote=f"Quote {i}",
            sentiment=s,
            source_id="src_1",
            stakeholder_tier="third_party",
        )
        for i, s in enumerate(sentiments)
    ]
    return ReactionsModule.model_construct(
        kind="reactions",
        module_id="mod_reactions",
        serves_needs=["world_reaction"],
        citations=[],
        confidence=_make_confidence(),
        slot="primary",
        artifact="ReactionsList",
        artifact_alternatives=[],
        inclusion_reason="medium",
        data=ReactionsData(items=items),
    )


def test_flag_reactions_single_sentiment():
    mod = _make_reactions_module(["positive"] * 5)
    flagged = _flag_reactions_sentiment(mod)
    assert "single_sentiment_perspective" in flagged.confidence.flags


def test_flag_reactions_multiple_sentiments_no_flag():
    mod = _make_reactions_module(
        ["positive", "negative", "positive", "neutral", "negative"]
    )
    flagged = _flag_reactions_sentiment(mod)
    assert "single_sentiment_perspective" not in flagged.confidence.flags


def test_flag_reactions_non_reactions_pass_through():
    hero = _make_hero_module()
    assert _flag_reactions_sentiment(hero) is hero
