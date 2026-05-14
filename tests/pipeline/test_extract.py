"""Tests for Stage 5 — Module extraction (parallel, per-kind, need-aware)."""

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
    FetchQuery,
    InfoboxData,
    InfoboxRow,
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


def _make_need_plan(
    module_kinds: list[str] | None = None,
    time_range_days: int = 14,
) -> NeedPlanOutput:
    """Build a NeedPlanOutput where need #1 (what_happened) is activated and
    carries all the requested module_kinds. Other 7 needs are deactivated
    placeholders so the rank-permutation invariant holds."""
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
                fetch_queries=(
                    [FetchQuery(query="q", time_range_days=time_range_days)]
                    if idx == 0
                    else []
                ),
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
        primary_entity="GPT-5.5 Instant (OpenAI)",
        event_type_hint="product_launch",
        temporal_posture="recent",
    )


def _openrouter_envelope(
    content_json: str, model: str = "anthropic/claude-haiku-4-5"
) -> dict:
    return {
        "id": "gen-test-extract",
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content_json},
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
# Test 1: _filter_evidence applies a coarse recency window only.
# ---------------------------------------------------------------------------
def test_filter_evidence_drops_sources_older_than_2x_window():
    now = datetime.now(timezone.utc)
    recent = _make_source("src_recent", published_at=now.isoformat())
    old = _make_source(
        "src_old",
        published_at=(now - timedelta(days=60)).isoformat(),
    )
    plan = _make_need_plan(time_range_days=14)  # cutoff = 2 * 14 = 28 days
    result = _filter_evidence([recent, old], plan)
    ids = {s.id for s in result}
    assert "src_recent" in ids
    assert "src_old" not in ids


def test_filter_evidence_falls_back_to_full_pool_when_nothing_matches():
    """If no sources pass the recency filter, return the full pool."""
    now = datetime.now(timezone.utc)
    old = _make_source("src_only", published_at=(now - timedelta(days=400)).isoformat())
    plan = _make_need_plan(time_range_days=7)
    assert _filter_evidence([old], plan) == [old]


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
    assert _collect_cited_ids(data) == {"src_x", "src_y"}


def test_collect_cited_ids_handles_empty():
    assert _collect_cited_ids(InfoboxData(rows=[])) == set()


# ---------------------------------------------------------------------------
# Test 3: extract_one_module skips when cited_ids not in evidence pool
# ---------------------------------------------------------------------------
@respx.mock
async def test_extract_one_module_skips_when_cited_ids_unknown(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    content = _valid_infobox_json(source_id="src_unknown")
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_openrouter_envelope(content))
    )

    from generator.modules import all_modules

    infobox_cls = next(cls for cls in all_modules() if cls.kind == "infobox")
    module = infobox_cls()

    evidence = [_make_source("src_1")]
    plan = _make_need_plan(["infobox"])
    ctx = PlanContext(
        subject=_make_subject(), need_plan=plan, aesthetic=_make_aesthetic()
    )

    result = await extract_one_module(module, ctx, evidence)
    assert result is None


# ---------------------------------------------------------------------------
# Test 4: extract_one_module skips when should_render returns False
# ---------------------------------------------------------------------------
@respx.mock
async def test_extract_one_module_skips_when_should_render_false(monkeypatch):
    """InfoboxModule.should_render requires >= 3 rows; return 2 → skip."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

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
    plan = _make_need_plan(["infobox"])
    ctx = PlanContext(
        subject=_make_subject(), need_plan=plan, aesthetic=_make_aesthetic()
    )

    result = await extract_one_module(module, ctx, evidence)
    assert result is None


# ---------------------------------------------------------------------------
# Test 5: run returns only successful modules
# ---------------------------------------------------------------------------
@respx.mock
async def test_run_returns_only_successful_modules(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    evidence = [_make_source("src_1"), _make_source("src_2", publisher_name="Wired")]
    plan = _make_need_plan(["hero", "infobox", "schedule"])

    def side_effect(request):
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
            return httpx.Response(200, json=_openrouter_envelope("NOT VALID JSON {{{"))

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=side_effect
    )

    result = await run(
        need_plan=plan,
        aesthetic=_make_aesthetic(),
        subject=_make_subject(),
        evidence_pool=evidence,
    )
    assert len(result) == 2
    kinds = {m.kind for m in result}
    assert "hero" in kinds
    assert "infobox" in kinds
    assert "schedule" not in kinds


# ---------------------------------------------------------------------------
# Test 6: run only dispatches kinds in assigned_modules
# ---------------------------------------------------------------------------
@respx.mock
async def test_run_only_dispatches_kinds_in_plan(monkeypatch):
    """Plan with only 'hero' assigned → exactly 1 LLM call."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()

    evidence = [_make_source("src_1")]
    plan = _make_need_plan(["hero"])

    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200, json=_openrouter_envelope(_valid_hero_json("src_1"))
        )
    )

    await run(
        need_plan=plan,
        aesthetic=_make_aesthetic(),
        subject=_make_subject(),
        evidence_pool=evidence,
    )

    assert route.call_count == 1
