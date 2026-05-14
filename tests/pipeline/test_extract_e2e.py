"""End-to-end Stage 5 test: at least 7 of 12 modules succeed."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from generator.pipeline import extract
from generator.schema import (
    AestheticOverrides,
    AestheticPlanOutput,
    EventSubject,
    PlanComposition,
    PlanOutput,
    Source,
    SourceStrategy,
)


_FIXTURES = Path(__file__).parent.parent / "fixtures"
_EVIDENCE_PATH = _FIXTURES / "evidence" / "gpt55_instant.json"

ALL_KINDS = [
    "hero",
    "infobox",
    "schedule",
    "countdown",
    "kpi_numbers",
    "comparison",
    "changelog",
    "reactions",
    "media_coverage",
    "official_statements",
    "where_to_watch",
    "background",
]

# Map kind → data_schema.__name__ (the unique string in the request body's response_format block)
_KIND_TO_SCHEMA_NAME = {
    "hero": "HeroData",
    "infobox": "InfoboxData",
    "schedule": "ScheduleData",
    "countdown": "CountdownData",
    "kpi_numbers": "KPINumbersData",
    "comparison": "ComparisonData",
    "changelog": "ChangelogData",
    "reactions": "ReactionsData",
    "media_coverage": "MediaCoverageData",
    "official_statements": "OfficialStatementsData",
    "where_to_watch": "WhereToWatchData",
    "background": "BackgroundData",
}


@pytest.fixture
def evidence_gpt55() -> list[Source]:
    raw = json.loads(_EVIDENCE_PATH.read_text())
    return [Source.model_validate(s) for s in raw]


def _module_data_payload(kind: str, source_ids: list[str]) -> dict[str, Any]:
    """Build a minimal valid <Kind>Data dict for the kind, citing the given source_ids."""
    sid = source_ids[0]
    sid2 = source_ids[1] if len(source_ids) > 1 else sid
    if kind == "hero":
        return {
            "title": "GPT-5.5 Instant rolls out as ChatGPT default",
            "subtitle": "Faster, cheaper successor to GPT-5.3 Instant",
            "summary": "OpenAI made GPT-5.5 Instant the new default ChatGPT model in May 2026.",
            "image_alt": "OpenAI brand mark",
            "badge_label": "Product Launch",
        }
    if kind == "infobox":
        return {
            "rows": [
                {"label": "Vendor", "value": "OpenAI", "source_id": sid},
                {"label": "Released", "value": "May 2026", "source_id": sid},
                {"label": "Replaces", "value": "GPT-5.3 Instant", "source_id": sid2},
                {"label": "Surface", "value": "ChatGPT default", "source_id": sid},
                {"label": "Pricing", "value": "Same tier", "source_id": sid2},
            ]
        }
    if kind == "kpi_numbers":
        return {
            "tiles": [
                {
                    "value": "52.5%",
                    "label": "Fewer hallucinations",
                    "comparison": "vs GPT-5.3 Instant",
                    "source_id": sid,
                },
                {"value": "2x", "label": "Throughput", "source_id": sid2},
            ]
        }
    if kind == "comparison":
        return {
            "subjects": [
                {"name": "GPT-5.5 Instant", "label": "current"},
                {"name": "GPT-5.3 Instant", "label": "previous"},
            ],
            "axes": [
                {
                    "label": "Latency",
                    "cells": [
                        {"value": "fast", "source_id": sid},
                        {"value": "slower", "source_id": sid2},
                    ],
                },
                {
                    "label": "Cost",
                    "cells": [
                        {"value": "lower", "source_id": sid},
                        {"value": "baseline", "source_id": sid2},
                    ],
                },
            ],
        }
    if kind == "changelog":
        return {
            "version_label": "GPT-5.5 Instant",
            "previous_version_label": "GPT-5.3 Instant",
            "entries": [
                {
                    "label": "Memory control",
                    "description": "Per-conversation memory sources control panel",
                    "importance": "feature",
                    "source_id": sid,
                },
                {
                    "label": "Faster Instant tier",
                    "description": "Lower latency on default-tier responses",
                    "importance": "feature",
                    "source_id": sid2,
                },
            ],
        }
    if kind == "reactions":
        return {
            "items": [
                {
                    "author": f"Reviewer {i}",
                    "author_role": "Tech journalist",
                    "quote": f"Notable reaction {i} about GPT-5.5 Instant launch from OpenAI.",
                    "sentiment": "positive" if i % 2 == 0 else "neutral",
                    "source_id": sid if i % 2 == 0 else sid2,
                }
                for i in range(5)
            ]
        }
    if kind == "media_coverage":
        return {
            "items": [
                {
                    "headline": f"Headline {i}: GPT-5.5 Instant launches",
                    "publisher": f"Outlet {i}",
                    "publisher_tier": "T1",
                    "published_at": "2026-05-12T10:00:00+00:00",
                    "url": f"https://example.com/story{i}",
                    "snippet": "Coverage snippet about the GPT-5.5 Instant rollout by OpenAI.",
                    "source_id": sid if i % 2 == 0 else sid2,
                }
                for i in range(5)
            ],
            "grouping_strategy": "flat",
        }
    if kind == "official_statements":
        return {
            "items": [
                {
                    "author": "Sam Altman",
                    "role": "CEO",
                    "organization": "OpenAI",
                    "quote": "GPT-5.5 Instant raises the bar for the default ChatGPT experience.",
                    "made_at": "2026-05-12T15:00:00+00:00",
                    "source_url": "https://openai.com/blog/gpt55-instant",
                    "source_id": sid,
                },
            ]
        }
    if kind == "background":
        return {
            "paragraphs": [
                {
                    "text": "GPT-5.5 Instant succeeds GPT-5.3 Instant as the default ChatGPT model.",
                    "citations": [
                        {"source_id": sid, "claim_text": "Rollout in May 2026."}
                    ],
                },
            ]
        }
    if kind == "schedule":
        # Empty items → should_render returns False → legitimately skipped
        return {"items": [], "timezone": "America/Los_Angeles"}
    if kind == "countdown":
        return {
            "target_at": "2026-06-01T00:00:00+00:00",
            "label": "next milestone",
            "source_id": sid,
        }
    if kind == "where_to_watch":
        # Empty channels → should_render returns False → legitimately skipped
        return {"channels": []}
    raise KeyError(kind)


def _mock_response(kind: str, source_ids: list[str]) -> dict[str, Any]:
    """Wrap module data as an OpenRouter chat-completion response."""
    return {
        "id": f"gen-{kind}",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": json.dumps(_module_data_payload(kind, source_ids)),
                },
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 80},
    }


def _ctx_for_product_launch():
    subject = EventSubject(
        primary_entity="GPT-5.5 Instant (OpenAI)",
        event_type_hint="product_launch",
        temporal_posture="recent",
        time_anchor="2026-05-12T00:00:00+00:00",
    )
    composition = [
        PlanComposition(
            module_kind=k,
            artifact={
                "hero": "HeroBanner",
                "infobox": "Infobox",
                "schedule": "ScheduleList",
                "countdown": "Countdown",
                "kpi_numbers": "KPITiles",
                "comparison": "ComparisonTable",
                "changelog": "Changelog",
                "reactions": "ReactionsList",
                "media_coverage": "CoverageList",
                "official_statements": "StatementsList",
                "where_to_watch": "ChannelList",
                "background": "Prose",
            }[k],
            slot="primary",
            priority="medium",
            artifact_alternatives=[],
        )
        for k in ALL_KINDS
    ]
    plan = PlanOutput(
        archetype_hint="product_launch",
        layout_preset_id="product_focus",
        composition=composition,
        source_strategy=SourceStrategy(
            preferred_tiers=["T0", "T1", "T2"],
            time_range_days=14,
            min_publishers=2,
        ),
    )
    aesthetic = AestheticPlanOutput(
        preset_id="product_focus",
        preset_confidence=0.9,
        alternatives_considered=[],
        aesthetic_overrides=AestheticOverrides(),
        reasoning="product launch fits product_focus",
    )
    return subject, plan, aesthetic


@respx.mock
@pytest.mark.asyncio
async def test_e2e_at_least_seven_modules_succeed(monkeypatch, evidence_gpt55):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    pool_ids = [s.id for s in evidence_gpt55]

    # Build reverse-lookup: schema_name → kind
    schema_name_to_kind = {v: k for k, v in _KIND_TO_SCHEMA_NAME.items()}

    def route_handler(request: httpx.Request) -> httpx.Response:
        body = request.read().decode()
        # The request body includes `"name": "<SchemaClassName>"` in the
        # response_format.json_schema block — use this as the reliable discriminator.
        for schema_name, kind in schema_name_to_kind.items():
            if f'"{schema_name}"' in body:
                return httpx.Response(200, json=_mock_response(kind, pool_ids))
        # Fallback: should never happen
        return httpx.Response(200, json=_mock_response("hero", pool_ids))

    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=route_handler
    )

    subject, plan, aesthetic = _ctx_for_product_launch()
    modules = await extract.run(plan, aesthetic, subject, evidence_gpt55)

    assert len(modules) >= 7, (
        f"only got {len(modules)} modules: {[m.kind for m in modules]}"
    )

    pool_id_set = set(pool_ids)
    for m in modules:
        for c in m.citations:
            assert c.source_id in pool_id_set, (
                f"module {m.kind} cited unknown source_id {c.source_id}"
            )
        assert set(m.confidence.flags) <= {
            "single_source",
            "low_tier_only",
            "contested_fact",
        }, f"module {m.kind} has unexpected confidence flags: {m.confidence.flags}"
