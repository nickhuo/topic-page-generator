"""Block-extract stage: one LLM call per section, returning RenderedSection."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from generator.llm.trace_buffer import reset
from generator.pipeline.block_extract import (
    extract_one_section,
    run_block_extract_stage,
)
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    RenderedSection,
    SectionPlan,
    Source,
    SourceRights,
)

FIX = Path(__file__).parent.parent / "fixtures"


def _section(sid="overview", block="paragraph") -> SectionPlan:
    return SectionPlan(
        section_id=sid,
        kind="backbone",
        title=sid.title(),
        rank=1,
        block_kind=block,  # type: ignore[arg-type]
        intent="i",
        acceptance=AcceptanceCriteria(description="d"),
    )


def _source(sid: str = "s1") -> Source:
    return Source(
        id=sid,
        url="https://reuters.com/a",
        publisher=Publisher(name="Reuters", tier="T1"),
        title="t",
        published_at="2026-03-19T12:00:00Z",
        fetched_at="2026-03-19T13:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )


@respx.mock
async def test_extract_one_paragraph_section(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_block_paragraph_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    rs = await extract_one_section(
        section=_section(),
        sources=[_source()],
        canonical_title="t",
    )
    assert isinstance(rs, RenderedSection)
    assert rs.section_id == "overview"
    assert rs.block_kind == "paragraph"
    assert rs.block_data.kind == "paragraph"
    assert rs.eval_passed is True


@respx.mock
async def test_extract_one_timeline_section(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_block_timeline_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    rs = await extract_one_section(
        section=_section("timeline", "timeline"),
        sources=[_source()],
        canonical_title="t",
    )
    assert rs is not None
    assert rs.block_kind == "timeline"
    assert rs.block_data.kind == "timeline"


@respx.mock
async def test_extract_drops_section_when_minimum_viable_fails(monkeypatch):
    """If the block fails BlockSpec.is_minimum_viable, the section is dropped (None)."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    # Empty-paragraph response — paragraph spec rejects all-whitespace.
    envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "{\"kind\":\"paragraph\",\"style\":\"prose\",\"paragraphs_md\":[\"   \"],\"pull_quotes\":[],\"citations\":[]}",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=envelope)
    )
    rs = await extract_one_section(
        section=_section(), sources=[_source()], canonical_title="t"
    )
    assert rs is None


@respx.mock
async def test_extract_drops_section_with_uncited_source_id(monkeypatch):
    """If the LLM cites s2 but s2 isn't in the evidence pool, drop the section."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "{\"kind\":\"paragraph\",\"style\":\"prose\",\"paragraphs_md\":[\"Something real.\"],\"pull_quotes\":[],\"citations\":[{\"source_id\":\"s_FAKE\"}]}",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 10, "total_tokens": 110},
    }
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=envelope)
    )
    rs = await extract_one_section(
        section=_section(), sources=[_source("s1")], canonical_title="t"
    )
    assert rs is None


async def test_run_block_extract_stage_parallel(monkeypatch):
    """run_block_extract_stage gathers all sections in parallel and drops None results."""

    async def fake_extract(*, section, sources, canonical_title, model=None):
        from generator.blocks.schema import ParagraphBlockData
        if section.section_id == "drop":
            return None
        return RenderedSection(
            section_id=section.section_id,
            block_kind="paragraph",
            block_data=ParagraphBlockData(paragraphs_md=["x"]),
        )

    monkeypatch.setattr(
        "generator.pipeline.block_extract.extract_one_section", fake_extract
    )
    out = await run_block_extract_stage(
        sections=[_section("a"), _section("drop"), _section("b")],
        evidence_by_section={"a": [_source()], "drop": [_source()], "b": [_source()]},
        canonical_title="t",
    )
    ids = [r.section_id for r in out]
    assert ids == ["a", "b"]
