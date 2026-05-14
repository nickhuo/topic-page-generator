"""Tests for Stage 5 — Module extraction (parallel, per-kind)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import httpx
import respx

from generator.llm.trace_buffer import reset
from generator.modules.base import PlanContext
from generator.pipeline.extract import (
    _collect_cited_ids,
    _filter_evidence,
    extract_one_module,
    run,
)
from generator.schema import (
    AestheticOverrides,
    AestheticPlanOutput,
    EventSubject,
    InfoboxData,
    InfoboxRow,
    PlanComposition,
    PlanOutput,
    Publisher,
    Source,
    SourceRights,
    SourceStrategy,
)


# ---------------------------------------------------------------------------
# Shared helpers / fixtures
# ---------------------------------------------------------------------------


def _make_source(
    sid: str,
    tier: str = "T0",
    publisher_name: str = "TechCrunch",
    published_at: str | None = None,
) -> Source:
    if published_at is None:
        published_at = datetime.now(timezone.utc).isoformat()
    return Source(
        id=sid,
        url="https://example.com/article",
        publisher=Publisher(name=publisher_name, tier=tier),
        title=f"Article {sid}",
        published_at=published_at,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        language="en",
        rights=SourceRights(max_excerpt_words=100, can_paraphrase=True),
    )


def _make_plan(
    module_kinds: list[str] | None = None,
    preferred_tiers: list[str] | None = None,
    time_range_days: int = 14,
) -> PlanOutput:
    if module_kinds is None:
        module_kinds = ["hero", "infobox"]
    if preferred_tiers is None:
        preferred_tiers = ["T0", "T1"]
    composition = [
        PlanComposition(
            module_kind=kind,
            artifact="HeroBanner" if kind == "hero" else "Infobox",
            slot="hero" if kind == "hero" else "aside",
            priority="required",
        )
        for kind in module_kinds
    ]
    return PlanOutput(
        archetype_hint="product_launch",
        layout_preset_id="product_focus",
        composition=composition,
        source_strategy=SourceStrategy(
            preferred_tiers=preferred_tiers,
            time_range_days=time_range_days,
            min_publishers=1,
        ),
    )


def _make_aesthetic() -> AestheticPlanOutput:
    return AestheticPlanOutput(
        preset_id="product_focus",
        preset_confidence=0.9,
        aesthetic_overrides=AestheticOverrides(),
        reasoning="test",
    )


def _make_subject() -> EventSubject:
    return EventSubject(
        primary_entity="GPT-5.5 Instant (OpenAI)",
        event_type_hint="product_launch",
        temporal_posture="recent",
    )


def _openrouter_envelope(
    content_json: str, model: str = "anthropic/claude-haiku-4-5"
) -> dict:
    """Wrap a JSON string in an OpenRouter chat-completion response envelope."""
    return {
        "id": "gen-test-extract",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content_json,
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 200, "completion_tokens": 100, "total_tokens": 300},
    }


def _valid_hero_json(source_id: str = "src_1") -> str:
    return json.dumps(
        {
            "title": "GPT-5.5 Instant is Now ChatGPT Default",
            "subtitle": "OpenAI makes the switch in May 2026",
            "summary": "OpenAI set GPT-5.5 Instant as the default ChatGPT model.",
            "image_url": None,
            "image_alt": "OpenAI logo",
            "badge_label": "PRODUCT LAUNCH",
        }
    )


def _valid_infobox_json(source_id: str = "src_1") -> str:
    return json.dumps(
        {
            "rows": [
                {"label": "Vendor", "value": "OpenAI", "source_id": source_id},
                {"label": "Release", "value": "May 2026", "source_id": source_id},
                {
                    "label": "Replaces",
                    "value": "GPT-5.3 Instant",
                    "source_id": source_id,
                },
                {
                    "label": "Surface",
                    "value": "ChatGPT default",
                    "source_id": source_id,
                },
                {"label": "Pricing", "value": "Same tiers", "source_id": source_id},
            ]
        }
    )


# ---------------------------------------------------------------------------
# Test 1: _filter_evidence respects preferred_tiers and recency
# ---------------------------------------------------------------------------


def test_filter_evidence_respects_preferred_tiers_and_recency():
    now = datetime.now(timezone.utc)
    recent_t0 = _make_source("src_good_t0", tier="T0", published_at=now.isoformat())
    recent_t2 = _make_source("src_good_t2", tier="T2", published_at=now.isoformat())
    old_t0 = _make_source(
        "src_old_t0",
        tier="T0",
        published_at=(now - timedelta(days=60)).isoformat(),
    )
    recent_t3 = _make_source("src_t3", tier="T3", published_at=now.isoformat())

    plan = _make_plan(preferred_tiers=["T0", "T1"], time_range_days=14)
    # cutoff = now - 28 days; preferred_tiers = T0/T1

    result = _filter_evidence([recent_t0, recent_t2, old_t0, recent_t3], plan)
    ids = {s.id for s in result}

    assert "src_good_t0" in ids  # T0, recent — passes
    assert "src_good_t2" not in ids  # T2, not in preferred_tiers
    assert "src_old_t0" not in ids  # T0 but too old (60d > 28d cutoff)
    assert "src_t3" not in ids  # T3, not in preferred_tiers


def test_filter_evidence_falls_back_to_full_pool_when_nothing_matches():
    """If no sources pass the filter, return the full pool rather than an empty list."""
    now = datetime.now(timezone.utc)
    src = _make_source("src_only", tier="T3", published_at=now.isoformat())
    plan = _make_plan(preferred_tiers=["T0"], time_range_days=7)
    result = _filter_evidence([src], plan)
    assert result == [src]


# ---------------------------------------------------------------------------
# Test 2: _collect_cited_ids walks pydantic tree
# ---------------------------------------------------------------------------


def test_collect_cited_ids_walks_pydantic_tree():
    data = InfoboxData(
        rows=[
            InfoboxRow(label="Vendor", value="OpenAI", source_id="src_x"),
            InfoboxRow(label="Date", value="May 2026", source_id="src_y"),
        ]
    )
    ids = _collect_cited_ids(data)
    assert ids == {"src_x", "src_y"}


def test_collect_cited_ids_handles_empty():
    data = InfoboxData(rows=[])
    ids = _collect_cited_ids(data)
    assert ids == set()


# ---------------------------------------------------------------------------
# Test 3: extract_one_module skips when cited_ids not in evidence pool
# ---------------------------------------------------------------------------


@respx.mock
async def test_extract_one_module_skips_when_cited_ids_unknown(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    # LLM returns infobox data citing src_unknown which is NOT in the evidence pool
    content = _valid_infobox_json(source_id="src_unknown")
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_openrouter_envelope(content))
    )

    from generator.modules import all_modules

    infobox_cls = next(cls for cls in all_modules() if cls.kind == "infobox")
    module = infobox_cls()

    evidence = [_make_source("src_1")]  # only src_1 in pool
    plan = _make_plan(["infobox"])
    ctx = PlanContext(subject=_make_subject(), plan=plan, aesthetic=_make_aesthetic())

    result = await extract_one_module(module, ctx, evidence)
    assert result is None


# ---------------------------------------------------------------------------
# Test 4: extract_one_module skips when should_render returns False
# ---------------------------------------------------------------------------


@respx.mock
async def test_extract_one_module_skips_when_should_render_false(monkeypatch):
    """InfoboxModule.should_render requires >= 3 rows; return empty rows → skip."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    # Return an infobox with only 2 rows — should_render will return False
    sparse_infobox = json.dumps(
        {
            "rows": [
                {"label": "Vendor", "value": "OpenAI", "source_id": "src_1"},
                {"label": "Date", "value": "May 2026", "source_id": "src_1"},
            ]
        }
    )
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_openrouter_envelope(sparse_infobox))
    )

    from generator.modules import all_modules

    infobox_cls = next(cls for cls in all_modules() if cls.kind == "infobox")
    module = infobox_cls()

    evidence = [_make_source("src_1")]
    plan = _make_plan(["infobox"])
    ctx = PlanContext(subject=_make_subject(), plan=plan, aesthetic=_make_aesthetic())

    result = await extract_one_module(module, ctx, evidence)
    assert result is None


# ---------------------------------------------------------------------------
# Test 5: run returns only successful modules
# ---------------------------------------------------------------------------


@respx.mock
async def test_run_returns_only_successful_modules(monkeypatch):
    """hero+infobox succeed; schedule gets malformed JSON → only 2 modules returned."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    evidence = [_make_source("src_1"), _make_source("src_2", publisher_name="Wired")]
    plan = _make_plan(["hero", "infobox", "schedule"])

    def side_effect(request):
        # Detect which module is being extracted from the request body.
        # Each extraction_prompt_template starts with: "... for the "<Kind>" module ..."
        body = json.loads(request.content)
        user_message = next(
            m["content"] for m in body["messages"] if m["role"] == "user"
        )
        if '"Hero" module' in user_message:
            return httpx.Response(
                200, json=_openrouter_envelope(_valid_hero_json("src_1"))
            )
        elif '"Infobox" module' in user_message:
            return httpx.Response(
                200, json=_openrouter_envelope(_valid_infobox_json("src_1"))
            )
        else:
            # schedule → malformed JSON (triggers validation retry then LLMOutputError)
            return httpx.Response(200, json=_openrouter_envelope("NOT VALID JSON {{{"))

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=side_effect
    )

    result = await run(
        plan=plan,
        aesthetic=_make_aesthetic(),
        subject=_make_subject(),
        evidence_pool=evidence,
    )
    # hero and infobox succeed; schedule fails validation and is dropped
    assert len(result) == 2
    kinds = {m.kind for m in result}
    assert "hero" in kinds
    assert "infobox" in kinds
    assert "schedule" not in kinds


# ---------------------------------------------------------------------------
# Test 6: run only dispatches kinds in composition
# ---------------------------------------------------------------------------


@respx.mock
async def test_run_only_dispatches_kinds_in_composition(monkeypatch):
    """Composition with only 'hero' → exactly 1 LLM call."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    evidence = [_make_source("src_1")]
    plan = _make_plan(["hero"])

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json=_openrouter_envelope(_valid_hero_json("src_1"))
        )
    )

    await run(
        plan=plan,
        aesthetic=_make_aesthetic(),
        subject=_make_subject(),
        evidence_pool=evidence,
    )

    assert route.call_count == 1
