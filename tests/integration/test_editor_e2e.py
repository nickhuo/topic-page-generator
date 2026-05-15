"""Minimal end-to-end smoke test for the editor-architecture pipeline.

Proves that the full CLI pipeline (ground → curation → research → block_extract →
render → deliver) runs without error and writes the three expected output files.

All LLM calls are mocked via respx.  All external data-source helpers are
monkeypatched.  The test makes no assertions about HTML quality — only about
exit code and file presence.
"""

from __future__ import annotations

import json

import httpx
import respx
from typer.testing import CliRunner

from generator.cli import app

# ---------------------------------------------------------------------------
# Canned LLM response payloads
# ---------------------------------------------------------------------------

_GROUND_RESPONSE = {
    "id": "gen-e2e-ground",
    "model": "anthropic/claude-sonnet-4-6",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {
                        "is_hot_event": True,
                        "rejection_reason": None,
                        "facts": {
                            "entities": ["GPT-5.5 Instant (OpenAI)"],
                            "what": "OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT.",
                            "when": "2026-05-01T00:00:00Z",
                            "where": None,
                            "why": None,
                            "supporting_sources": ["s1"],
                        },
                        "canonical_title": "GPT-5.5 Instant rollout",
                        "confidence": 0.92,
                        "reasoning": "Fresh T0 source confirms named product release.",
                    }
                ),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 412, "completion_tokens": 87, "total_tokens": 499},
}

# Curation: return empty curated list so only backbone sections are used.
_CURATION_RESPONSE = {
    "id": "gen-e2e-curation",
    "object": "chat.completion",
    "model": "anthropic/claude-sonnet-4-6",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps({"sections": []}),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 200, "completion_tokens": 20, "total_tokens": 220},
}

# Research query: generic query stub.
_RESEARCH_QUERY_RESPONSE = {
    "id": "gen-e2e-query",
    "object": "chat.completion",
    "model": "anthropic/claude-haiku-4-5",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps({"query": "GPT-5.5 Instant OpenAI rollout 2026"}),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 200, "completion_tokens": 12, "total_tokens": 212},
}

# Research eval: immediately satisfied so no loop iteration.
_RESEARCH_EVAL_RESPONSE = {
    "id": "gen-e2e-eval",
    "object": "chat.completion",
    "model": "anthropic/claude-sonnet-4-6",
    "choices": [
        {
            "index": 0,
            "message": {
                "role": "assistant",
                "content": json.dumps(
                    {"satisfied": True, "gaps": [], "next_query_hint": None}
                ),
            },
            "finish_reason": "stop",
        }
    ],
    "usage": {"prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320},
}

# Block-extract responses keyed by Pydantic schema class name.
_BLOCK_PARAGRAPH_CONTENT = json.dumps(
    {
        "kind": "paragraph",
        "style": "prose",
        "paragraphs_md": [
            "OpenAI released GPT-5.5 Instant as the default ChatGPT model."
        ],
        "pull_quotes": [],
        "citations": [
            {"source_id": "s1", "claim_text": "OpenAI released GPT-5.5 Instant."}
        ],
    }
)

_BLOCK_TIMELINE_CONTENT = json.dumps(
    {
        "kind": "timeline",
        "entries": [
            {
                "title": "GPT-5.5 Instant announced",
                "time": "2026-05-01",
                "importance": "breaking",
                "source_id": "s1",
            },
            {
                "title": "Rollout completed",
                "time": "2026-05-02",
                "importance": "feature",
                "source_id": "s1",
            },
        ],
    }
)

_BLOCK_NEWSFEED_CONTENT = json.dumps(
    {
        "kind": "newsfeed",
        "cards": [
            {
                "url": "https://example.com/a1",
                "title": "OpenAI releases GPT-5.5 Instant",
                "publisher": "Example News",
                "tier": "T0",
                "source_id": "s1",
            },
            {
                "url": "https://example.com/a2",
                "title": "GPT-5.5 Instant now default in ChatGPT",
                "publisher": "Tech Review",
                "tier": "T1",
            },
        ],
        "variant": "news",
        "grouping": "flat",
    }
)

# Map from Pydantic schema class name → canned content string.
_BLOCK_SCHEMA_CONTENTS: dict[str, str] = {
    "ParagraphBlockData": _BLOCK_PARAGRAPH_CONTENT,
    "TimelineBlockData": _BLOCK_TIMELINE_CONTENT,
    "NewsfeedBlockData": _BLOCK_NEWSFEED_CONTENT,
}


def _block_response(schema_name: str) -> dict:
    content = _BLOCK_SCHEMA_CONTENTS.get(schema_name, _BLOCK_PARAGRAPH_CONTENT)
    return {
        "id": f"gen-e2e-block-{schema_name}",
        "object": "chat.completion",
        "model": "anthropic/claude-haiku-4-5",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 400, "completion_tokens": 60, "total_tokens": 460},
    }


# ---------------------------------------------------------------------------
# Request dispatcher — inspects outgoing LLM request to pick the right response
# ---------------------------------------------------------------------------


def _pick_response(request: httpx.Request) -> httpx.Response:
    """Return the appropriate canned response based on request body content."""
    try:
        body = json.loads(request.content)
    except Exception:
        return httpx.Response(200, json=_RESEARCH_EVAL_RESPONSE)

    # 1. Block-extract: identified by response_format.json_schema.name
    schema_name = (
        body.get("response_format", {}).get("json_schema", {}).get("name", "")
    )
    if schema_name in _BLOCK_SCHEMA_CONTENTS:
        return httpx.Response(200, json=_block_response(schema_name))

    # 2. Determine stage from system/user message content.
    messages = body.get("messages", [])
    all_text = " ".join(m.get("content", "") for m in messages)

    if "TASK: Ground" in all_text or "Ground a one-sentence event" in all_text:
        return httpx.Response(200, json=_GROUND_RESPONSE)

    if "curation planner" in all_text or "ALREADY CHOSEN" in all_text:
        return httpx.Response(200, json=_CURATION_RESPONSE)

    if "research judge" in all_text:
        return httpx.Response(200, json=_RESEARCH_EVAL_RESPONSE)

    if "single Tavily search query" in all_text or "Tavily search query" in all_text:
        return httpx.Response(200, json=_RESEARCH_QUERY_RESPONSE)

    # Default: research eval satisfied=True (prevents infinite loops).
    return httpx.Response(200, json=_RESEARCH_EVAL_RESPONSE)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(sid: str = "s1"):
    from generator.schema import Publisher, Source, SourceRights

    return Source(
        id=sid,
        url="https://example.com/article",
        publisher=Publisher(name="Example News", tier="T0"),
        title="Example article about GPT-5.5 Instant",
        published_at="2026-05-01T00:00:00Z",
        fetched_at="2026-05-01T00:01:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=1000, can_paraphrase=True),
        summary="OpenAI released GPT-5.5 Instant as the default ChatGPT model.",
    )


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


@respx.mock
def test_editor_pipeline_smoke(monkeypatch, tmp_path):
    """Full CLI run exits 0 and produces html, data.json, and trace.json."""
    # Env vars
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tav-test")

    # Redirect output directory so the test doesn't write to the real output/
    monkeypatch.setattr("generator.cli._OUTPUT_DIR", tmp_path)

    # Mock the OpenRouter endpoint
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        side_effect=_pick_response
    )

    # Stub external data-source helpers
    async def _fake_fetch_tavily(query, time_range_days=14, max_results=10, **kw):
        return [_make_source("s1")]

    async def _fake_fetch_wikidata(entity, **kw):
        return (None, {})

    async def _fake_fetch_wikipedia_card(title, **kw):
        return None

    # Patch in the source modules (where the names are defined)
    monkeypatch.setattr("generator.sources.tavily.fetch_tavily", _fake_fetch_tavily)
    monkeypatch.setattr("generator.sources.wikidata.fetch_wikidata", _fake_fetch_wikidata)
    monkeypatch.setattr(
        "generator.sources.wikipedia.fetch_wikipedia_card", _fake_fetch_wikipedia_card
    )

    # Also patch in the pipeline modules that imported these at import time
    import generator.pipeline.ground as _ground_mod
    import generator.pipeline.research as _research_mod

    monkeypatch.setattr(_ground_mod, "fetch_tavily", _fake_fetch_tavily)
    monkeypatch.setattr(_research_mod, "fetch_tavily", _fake_fetch_tavily)

    # Stub Brave Image Search — no key in CI; hero image gracefully absent.
    async def _fake_brave(query, *, count=5, timeout=12.0):
        return []  # mirror no-BRAVE_API_KEY path

    monkeypatch.setattr(
        "generator.pipeline.hero_image.fetch_brave_images", _fake_brave
    )

    # Invoke CLI
    runner = CliRunner()
    result = runner.invoke(
        app,
        ["run", "--auto", "OpenAI rolled out GPT-5.5 Instant as default in ChatGPT"],
    )

    assert result.exit_code == 0, (
        f"CLI exited {result.exit_code}.\n"
        f"Output:\n{result.output}\n"
        f"Exception: {result.exception!r}"
    )

    # Verify output files
    output_files = list(tmp_path.iterdir())
    html_files = [f for f in output_files if f.suffix == ".html"]
    data_files = [f for f in output_files if f.name.endswith(".data.json")]
    trace_files = [f for f in output_files if f.name.endswith(".trace.json")]

    assert html_files, f"Missing .html — found: {[f.name for f in output_files]}"
    assert data_files, f"Missing .data.json — found: {[f.name for f in output_files]}"
    assert trace_files, f"Missing .trace.json — found: {[f.name for f in output_files]}"

    # Basic content check: data.json has editorial_sections
    data = json.loads(data_files[0].read_text())
    assert "editorial_sections" in data, "data.json missing editorial_sections"
    assert len(data["editorial_sections"]) > 0, "editorial_sections is empty"
