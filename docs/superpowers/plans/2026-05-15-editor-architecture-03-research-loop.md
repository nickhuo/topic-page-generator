# Editor Architecture — Plan 3: Per-Section Research Loop

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** For each `SectionPlan` from Plan 2, run a capped `query → fetch → eval → refine` loop until `AcceptanceCriteria` are met or budget is exhausted. Behind `USE_EDITOR_ARCHITECTURE=1`. The old `run_fetch_stage` stays default.

**Architecture:** Three new pipeline modules + two prompts + one schema addition.

- `pipeline/research.py` — outer orchestrator. Per-section async tasks under a global Tavily counter. Prepends Wikidata + Wikipedia once. Returns `dict[section_id, list[Source]]`.
- `pipeline/research_eval.py` — LLM judge. Given a section + an evidence digest, decides `satisfied | gaps | next_query_hint`.
- `prompts/research_query.py` + `prompts/research_eval.py` — prompt builders.
- `Source.serves_sections: list[str]` — sibling field to existing `serves_needs`, populated by the new path.
- New schema `ResearchEvalResult` (response_model for the eval LLM call).

**Budgets (locked, env-overridable):**
- `MAX_ITERATIONS_PER_SECTION=3`
- `MAX_FETCH_CALLS_PER_SECTION=4`
- `MAX_TOTAL_TAVILY=30` (overrides the existing `MAX_TAVILY_CALLS` only when the editor flag is on)

**Tech Stack:** Python 3.12, Pydantic v2, pytest, asyncio, respx, monkeypatch.

---

## File map

**Create:**
- `src/generator/pipeline/research.py`
- `src/generator/pipeline/research_eval.py`
- `src/generator/prompts/research_query.py`
- `src/generator/prompts/research_eval.py`
- `tests/pipeline/test_research_query_prompt.py`
- `tests/pipeline/test_research_eval.py`
- `tests/pipeline/test_research_loop.py`
- `tests/fixtures/openrouter_research_eval_satisfied.json`
- `tests/fixtures/openrouter_research_eval_needs_more.json`
- `tests/fixtures/openrouter_research_query_refine.json`

**Modify:**
- `src/generator/schema.py` — append `ResearchEvalResult`; add `serves_sections: list[str]` to `Source`
- `src/generator/llm/client.py` — register `research_eval` and `research_query` stage fallbacks
- `src/generator/cli.py` — extend `USE_EDITOR_ARCHITECTURE` branch to call research loop and dump per-section evidence

---

## Task 1: Schema additions

**Files:**
- Modify: `src/generator/schema.py`
- Test: `tests/schema/test_research_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/schema/test_research_types.py`:

```python
"""Schema additions for the research loop."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from generator.schema import ResearchEvalResult, Source, Publisher, SourceRights


def test_research_eval_result_satisfied():
    r = ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None)
    assert r.satisfied is True
    assert r.gaps == []
    assert r.next_query_hint is None


def test_research_eval_result_unsatisfied_requires_gaps():
    """When satisfied=False, gaps must be non-empty — the LLM has to say why."""
    with pytest.raises(ValidationError):
        ResearchEvalResult(satisfied=False, gaps=[], next_query_hint=None)


def test_research_eval_result_unsatisfied_with_gaps():
    r = ResearchEvalResult(
        satisfied=False,
        gaps=["no source covers the timeline"],
        next_query_hint="GTC 2026 keynote timeline announcements",
    )
    assert r.satisfied is False
    assert len(r.gaps) >= 1


def test_source_serves_sections_defaults_to_empty():
    src = _source_factory()
    assert src.serves_sections == []


def test_source_serves_sections_roundtrip():
    src = _source_factory(serves_sections=["overview", "timeline"])
    assert src.serves_sections == ["overview", "timeline"]


def _source_factory(**overrides):
    base = dict(
        id="s1",
        url="https://example.com/a",
        publisher=Publisher(name="Example", tier="T1"),
        title="t",
        published_at="2026-05-15T12:00:00Z",
        fetched_at="2026-05-15T12:01:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )
    base.update(overrides)
    return Source(**base)
```

- [ ] **Step 2:** Run `uv run pytest tests/schema/test_research_types.py -v` — expect FAIL (ImportError + AttributeError for `serves_sections`).

- [ ] **Step 3: Add `serves_sections` to `Source`**

In `src/generator/schema.py`, find the `Source` class (around line 101). Add after the existing `serves_needs` line:

```python
    # Editor-architecture: which SectionPlan.section_id values this source backs.
    serves_sections: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Append `ResearchEvalResult`**

In `src/generator/schema.py`, append after the `SectionPlanOutput` block (around line 606):

```python
class ResearchEvalResult(_Frozen):
    """LLM judge output: is the section's evidence pool satisfactory?

    Used inside the per-section research loop. If `satisfied=False`, `gaps`
    must be non-empty (the LLM has to articulate what's missing) and
    `next_query_hint` is the LLM's best guess at what Tavily query would
    fill the gap.
    """

    satisfied: bool
    gaps: list[str] = Field(default_factory=list)
    next_query_hint: str | None = None

    @model_validator(mode="after")
    def _gaps_required_when_unsatisfied(self) -> ResearchEvalResult:
        if not self.satisfied and not self.gaps:
            raise ValueError(
                "ResearchEvalResult.satisfied=False requires at least one gap"
            )
        return self
```

(If `model_validator` is not yet imported in `schema.py`, add it: `from pydantic import model_validator`.)

- [ ] **Step 5:** Run `uv run pytest tests/schema/test_research_types.py -v` — expect PASS.

- [ ] **Step 6:** Run `uv run pytest -q` — confirm no regressions. The new `serves_sections` field is additive (default empty list).

- [ ] **Step 7: Commit**

```bash
git add src/generator/schema.py tests/schema/test_research_types.py
git commit -m "feat(schema): Source.serves_sections + ResearchEvalResult"
```

---

## Task 2: Research-query prompt

**Files:**
- Create: `src/generator/prompts/research_query.py`
- Test: `tests/pipeline/test_research_query_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_research_query_prompt.py`:

```python
"""Research-query prompt builder — produces a Tavily query from section context."""

from __future__ import annotations

from generator.prompts.research_query import build_research_query_messages
from generator.schema import (
    AcceptanceCriteria,
    EventFacts,
    SectionPlan,
)


def _facts() -> EventFacts:
    return EventFacts(
        entities=["NVIDIA"],
        what="GTC 2026 keynote",
        when="2026-03-19",
        where="San Jose",
        why="New architecture",
        supporting_sources=["s1"],
    )


def _section() -> SectionPlan:
    return SectionPlan(
        section_id="timeline",
        kind="backbone",
        title="Timeline",
        rank=3,
        block_kind="timeline",
        intent="3-7 milestones from announcement to keynote.",
        acceptance=AcceptanceCriteria(description="At least 3 milestone entries."),
    )


def test_initial_query_has_no_gap_context():
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        section=_section(),
        previous_gaps=None,
        previous_query=None,
    )
    user = msgs[1]["content"]
    assert "NVIDIA GTC 2026" in user
    assert "timeline" in user.lower()
    # No "previously tried" / "gap" block on first iteration
    assert "previous" not in user.lower()


def test_refine_query_includes_gaps_and_previous_query():
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        section=_section(),
        previous_gaps=["no source from before March 19"],
        previous_query="NVIDIA GTC 2026 announcements",
    )
    user = msgs[1]["content"]
    assert "no source from before March 19" in user
    assert "NVIDIA GTC 2026 announcements" in user


def test_output_format_directive_present():
    """The prompt must instruct the LLM to output a bare Tavily query string."""
    msgs = build_research_query_messages(
        facts=_facts(),
        canonical_title="t",
        section=_section(),
        previous_gaps=None,
        previous_query=None,
    )
    system = msgs[0]["content"]
    assert "query" in system.lower()
    assert "json" in system.lower() or "string" in system.lower()
```

- [ ] **Step 2:** Run pytest — expect FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

Create `src/generator/prompts/research_query.py`:

```python
"""Prompt builder for the research-query LLM call.

Used inside the per-section research loop. On iteration 1, produces an
initial Tavily query from the section's intent and acceptance criteria. On
iteration ≥2, refines based on `previous_gaps` and the `previous_query`
that didn't work.
"""

from __future__ import annotations

import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import EventFacts, SectionPlan

_INSTRUCTIONS = """\
You generate a single Tavily search query for one section of an event page.

Output a JSON object with one field:
  {"query": "..."}

Rules:
1. Query length: 4-12 words.
2. Anchor on the event's canonical title and the section's information need.
3. If the section's block_kind is "timeline", bias toward date-oriented terms
   ("when", "schedule", "announced", year/month).
4. If the section's block_kind is "newsfeed", bias toward publication terms
   ("coverage", "reactions", "analysis").
5. If the section's block_kind is "factsheet", bias toward reference terms
   ("specs", "details", "lineup", "list").
6. If previous_gaps and previous_query are supplied, your new query MUST
   differ meaningfully from previous_query and target one of the gaps.
"""


def build_research_query_messages(
    *,
    facts: EventFacts,
    canonical_title: str,
    section: SectionPlan,
    previous_gaps: list[str] | None,
    previous_query: str | None,
) -> list[dict]:
    user_payload = {
        "canonical_title": canonical_title,
        "entities": facts.entities,
        "what": facts.what,
        "when": facts.when,
        "where": facts.where,
        "section": {
            "section_id": section.section_id,
            "title": section.title,
            "block_kind": section.block_kind,
            "intent": section.intent,
            "acceptance": section.acceptance.description,
        },
    }
    if previous_gaps:
        user_payload["previous_gaps"] = previous_gaps
        user_payload["previous_query"] = previous_query

    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                "Generate one Tavily query for the following section.\n\n"
                + json.dumps(user_payload, indent=2)
                + '\n\nOUTPUT a JSON object {"query": "..."} now.'
            ),
        },
    ]


__all__ = ["build_research_query_messages"]
```

- [ ] **Step 4:** Run pytest — expect PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/generator/prompts/research_query.py tests/pipeline/test_research_query_prompt.py
git commit -m "feat(prompts): research-query prompt for per-section Tavily generation"
```

---

## Task 3: Research-eval prompt + stage

**Files:**
- Create: `src/generator/prompts/research_eval.py`
- Create: `src/generator/pipeline/research_eval.py`
- Modify: `src/generator/llm/client.py` — register `research_eval` and `research_query` fallback models
- Test: `tests/pipeline/test_research_eval.py`
- Test fixtures: `tests/fixtures/openrouter_research_eval_satisfied.json`, `tests/fixtures/openrouter_research_eval_needs_more.json`

- [ ] **Step 1: Add stage models**

In `src/generator/llm/client.py`, extend `_STAGE_FALLBACK_MODELS`:

```python
_STAGE_FALLBACK_MODELS = {
    "ground": "anthropic/claude-sonnet-4-6",
    "plan": "anthropic/claude-sonnet-4-6",
    "curation": "anthropic/claude-sonnet-4-6",
    "research_query": "anthropic/claude-haiku-4-5",
    "research_eval": "anthropic/claude-sonnet-4-6",
    "aesthetic": "anthropic/claude-haiku-4-5",
    "extract": "anthropic/claude-haiku-4-5",
    "consistency": "anthropic/claude-haiku-4-5",
}
```

- [ ] **Step 2: Build the canned fixtures**

Reuse the envelope shape from `tests/fixtures/openrouter_curation_happy.json`.

`tests/fixtures/openrouter_research_eval_satisfied.json`:
```json
{
  "id": "chatcmpl-fake-research-eval-ok",
  "object": "chat.completion",
  "model": "anthropic/claude-sonnet-4-6",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"satisfied\":true,\"gaps\":[],\"next_query_hint\":null}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 300, "completion_tokens": 20, "total_tokens": 320}
}
```

`tests/fixtures/openrouter_research_eval_needs_more.json`:
```json
{
  "id": "chatcmpl-fake-research-eval-gap",
  "object": "chat.completion",
  "model": "anthropic/claude-sonnet-4-6",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"satisfied\":false,\"gaps\":[\"no source covering the keynote date\"],\"next_query_hint\":\"NVIDIA GTC 2026 keynote date\"}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 300, "completion_tokens": 40, "total_tokens": 340}
}
```

- [ ] **Step 3: Write the failing test**

Create `tests/pipeline/test_research_eval.py`:

```python
"""Research-eval stage — LLM judge over a section's evidence pool."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import respx

from generator.llm.trace_buffer import reset
from generator.pipeline.research_eval import run_research_eval_stage
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    ResearchEvalResult,
    SectionPlan,
    Source,
    SourceRights,
)

FIX = Path(__file__).parent.parent / "fixtures"


def _section() -> SectionPlan:
    return SectionPlan(
        section_id="overview",
        kind="backbone",
        title="Overview",
        rank=1,
        block_kind="paragraph",
        intent="two paragraphs framing the event",
        acceptance=AcceptanceCriteria(description="who/what/when covered"),
    )


def _sources() -> list[Source]:
    return [
        Source(
            id="s1",
            url="https://reuters.com/a",
            publisher=Publisher(name="Reuters", tier="T1"),
            title="Headline",
            published_at="2026-03-19T12:00:00Z",
            fetched_at="2026-03-19T13:00:00Z",
            language="en",
            rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
            summary="Reuters reports on NVIDIA's GTC keynote.",
        ),
    ]


@respx.mock
async def test_eval_returns_satisfied(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_research_eval_satisfied.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await run_research_eval_stage(
        section=_section(), sources=_sources(), canonical_title="t"
    )
    assert isinstance(result, ResearchEvalResult)
    assert result.satisfied is True


@respx.mock
async def test_eval_returns_unsatisfied_with_gap(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_research_eval_needs_more.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    result = await run_research_eval_stage(
        section=_section(), sources=_sources(), canonical_title="t"
    )
    assert result.satisfied is False
    assert len(result.gaps) >= 1
    assert result.next_query_hint
```

- [ ] **Step 4:** Run pytest — expect FAIL (ModuleNotFoundError).

- [ ] **Step 5: Implement the prompt**

Create `src/generator/prompts/research_eval.py`:

```python
"""Prompt builder for the research-eval (judge) LLM call.

Given a section + evidence digest, the LLM decides whether the pool covers
the acceptance criteria or whether one more refined search is needed.
"""

from __future__ import annotations

import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import SectionPlan, Source

_INSTRUCTIONS = """\
You are a research judge. Given a section and the current evidence pool,
decide whether the pool satisfies the section's acceptance criteria.

Output a JSON object:
  {"satisfied": true|false, "gaps": ["..."], "next_query_hint": "..." | null}

Rules:
1. Set satisfied=true only if the pool covers every facet listed in the
   section's acceptance criteria description, AND distinct-source / distinct-
   publisher counts meet min_sources / min_publishers.
2. If satisfied=false, "gaps" MUST list at least one specific concrete
   missing facet (e.g. "no source from before the announcement",
   "all sources from a single publisher").
3. "next_query_hint" is a one-line natural-language hint for the next
   Tavily query — a person reading it should be able to type a query that
   probably fills the gap.
4. Do not output reasoning outside the JSON object.
"""


def build_research_eval_messages(
    *,
    section: SectionPlan,
    sources: list[Source],
    canonical_title: str,
) -> list[dict]:
    digest = [
        {
            "id": s.id,
            "publisher": s.publisher.name,
            "tier": s.publisher.tier,
            "title": s.title,
            "published_at": s.published_at,
            "summary": (s.summary or "")[:240],
        }
        for s in sources
    ]
    user_payload = {
        "canonical_title": canonical_title,
        "section": {
            "section_id": section.section_id,
            "title": section.title,
            "block_kind": section.block_kind,
            "intent": section.intent,
            "acceptance": {
                "description": section.acceptance.description,
                "min_sources": section.acceptance.min_sources,
                "min_publishers": section.acceptance.min_publishers,
                "required_facets": section.acceptance.required_facets,
                "forbid_single_perspective": section.acceptance.forbid_single_perspective,
            },
        },
        "evidence": digest,
    }
    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                "Evaluate whether this evidence pool satisfies the section.\n\n"
                + json.dumps(user_payload, indent=2)
                + "\n\nOUTPUT a ResearchEvalResult JSON now."
            ),
        },
    ]


__all__ = ["build_research_eval_messages"]
```

- [ ] **Step 6: Implement the stage**

Create `src/generator/pipeline/research_eval.py`:

```python
"""Research-eval stage — one LLM call per loop iteration.

The LLM acts as a judge over the current evidence pool for a single section.
"""

from __future__ import annotations

from generator.llm.client import call_structured, get_default_model
from generator.prompts.research_eval import build_research_eval_messages
from generator.schema import ResearchEvalResult, SectionPlan, Source


async def run_research_eval_stage(
    *,
    section: SectionPlan,
    sources: list[Source],
    canonical_title: str,
    model: str | None = None,
) -> ResearchEvalResult:
    resolved_model = model or get_default_model("research_eval")
    messages = build_research_eval_messages(
        section=section, sources=sources, canonical_title=canonical_title
    )
    return await call_structured(
        model=resolved_model,
        messages=messages,
        response_model=ResearchEvalResult,
    )


__all__ = ["run_research_eval_stage"]
```

- [ ] **Step 7:** Run pytest — expect PASS (2 tests).

- [ ] **Step 8: Commit**

```bash
git add src/generator/llm/client.py src/generator/prompts/research_eval.py src/generator/pipeline/research_eval.py tests/pipeline/test_research_eval.py tests/fixtures/openrouter_research_eval_satisfied.json tests/fixtures/openrouter_research_eval_needs_more.json
git commit -m "feat(pipeline): research-eval LLM judge stage"
```

---

## Task 4: Per-section research loop (the heart of Plan 3)

**Files:**
- Create: `src/generator/pipeline/research.py`
- Test: `tests/pipeline/test_research_loop.py`
- Test fixture: `tests/fixtures/openrouter_research_query_refine.json`

- [ ] **Step 1: Add the query-refine canned fixture**

`tests/fixtures/openrouter_research_query_refine.json`:
```json
{
  "id": "chatcmpl-fake-query",
  "object": "chat.completion",
  "model": "anthropic/claude-haiku-4-5",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"query\":\"NVIDIA GTC 2026 keynote date schedule\"}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 200, "completion_tokens": 12, "total_tokens": 212}
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/pipeline/test_research_loop.py`:

```python
"""Per-section research loop with budget caps."""

from __future__ import annotations

import asyncio

import pytest

from generator.pipeline.research import (
    DEFAULT_MAX_FETCH_CALLS_PER_SECTION,
    DEFAULT_MAX_ITERATIONS_PER_SECTION,
    DEFAULT_MAX_TOTAL_TAVILY,
    ResearchBudget,
    run_research_stage,
)
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    ResearchEvalResult,
    SectionPlan,
    Source,
    SourceRights,
)


def _section(sid: str = "overview", block: str = "paragraph") -> SectionPlan:
    return SectionPlan(
        section_id=sid,
        kind="backbone",
        title=sid.title(),
        rank=1,
        block_kind=block,  # type: ignore[arg-type]
        intent="i",
        acceptance=AcceptanceCriteria(description="cover the basics"),
    )


def _fake_source(url: str, pub: str = "Reuters") -> Source:
    return Source(
        id="s_" + str(abs(hash(url)))[:6],
        url=url,
        publisher=Publisher(name=pub, tier="T1"),
        title="t",
        published_at="2026-03-19T12:00:00Z",
        fetched_at="2026-03-19T13:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )


def test_default_budgets():
    assert DEFAULT_MAX_ITERATIONS_PER_SECTION == 3
    assert DEFAULT_MAX_FETCH_CALLS_PER_SECTION == 4
    assert DEFAULT_MAX_TOTAL_TAVILY == 30


async def test_loop_exits_when_eval_satisfied_first_iteration(monkeypatch):
    """If eval returns satisfied=True on iteration 1, no refinement happens."""
    call_log: dict[str, int] = {"tavily": 0, "eval": 0, "query": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        call_log["eval"] += 1
        return ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None)

    async def fake_query(**_):
        call_log["query"] += 1
        return "initial query"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr("generator.pipeline.research.run_research_eval_stage", fake_eval)
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    result = await run_research_stage(
        sections=[_section()],
        canonical_title="t",
        facts=None,  # not used by fakes
        seed_sources=[],
    )
    assert call_log["query"] == 1
    assert call_log["tavily"] == 1
    assert call_log["eval"] == 1
    assert "overview" in result
    assert result["overview"]


async def test_loop_iterates_when_eval_unsatisfied(monkeypatch):
    """When eval is unsatisfied, the loop refines query and runs again."""
    eval_returns = iter([
        ResearchEvalResult(satisfied=False, gaps=["x"], next_query_hint="more"),
        ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None),
    ])
    call_log = {"tavily": 0, "eval": 0, "query": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        call_log["eval"] += 1
        return next(eval_returns)

    async def fake_query(**_):
        call_log["query"] += 1
        return f"q{call_log['query']}"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr("generator.pipeline.research.run_research_eval_stage", fake_eval)
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    await run_research_stage(
        sections=[_section()], canonical_title="t", facts=None, seed_sources=[]
    )
    assert call_log["eval"] == 2
    assert call_log["tavily"] == 2
    assert call_log["query"] == 2  # initial + refine


async def test_loop_respects_max_iterations(monkeypatch):
    """Eval that never returns satisfied still terminates at MAX_ITERATIONS."""
    call_log = {"eval": 0, "tavily": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        call_log["eval"] += 1
        return ResearchEvalResult(
            satisfied=False, gaps=["always more"], next_query_hint="more"
        )

    async def fake_query(**_):
        return "q"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr("generator.pipeline.research.run_research_eval_stage", fake_eval)
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    await run_research_stage(
        sections=[_section()],
        canonical_title="t",
        facts=None,
        seed_sources=[],
        budget=ResearchBudget(max_iterations_per_section=2),
    )
    assert call_log["eval"] == 2
    assert call_log["tavily"] == 2


async def test_global_tavily_cap_across_sections(monkeypatch):
    """Sum of Tavily calls across all sections never exceeds budget.max_total_tavily."""
    call_log = {"tavily": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        return ResearchEvalResult(
            satisfied=False, gaps=["always more"], next_query_hint="m"
        )

    async def fake_query(**_):
        return "q"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr("generator.pipeline.research.run_research_eval_stage", fake_eval)
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    # 6 sections, each would naturally want max_iterations=3 → 18 calls; cap at 5.
    sections = [_section(sid=f"s{i}") for i in range(6)]
    await run_research_stage(
        sections=sections,
        canonical_title="t",
        facts=None,
        seed_sources=[],
        budget=ResearchBudget(max_total_tavily=5, max_iterations_per_section=3),
    )
    assert call_log["tavily"] <= 5


async def test_seed_sources_prepended_to_every_section(monkeypatch):
    """Wikidata/Wikipedia seed sources are visible to every section's eval."""
    seen_sources_per_eval: list[list[str]] = []

    async def fake_tavily(query, **_):
        return [_fake_source("https://t.example/x")]

    async def fake_eval(**kwargs):
        seen_sources_per_eval.append([s.id for s in kwargs["sources"]])
        return ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None)

    async def fake_query(**_):
        return "q"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr("generator.pipeline.research.run_research_eval_stage", fake_eval)
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    seed = [_fake_source("https://wikidata.org/wiki/Q1", pub="Wikidata")]
    seed[0] = seed[0].model_copy(update={"id": "seed1"})

    await run_research_stage(
        sections=[_section("s1"), _section("s2")],
        canonical_title="t",
        facts=None,
        seed_sources=seed,
    )
    assert all("seed1" in ids for ids in seen_sources_per_eval)
```

- [ ] **Step 3:** Run pytest — expect FAIL (ModuleNotFoundError).

- [ ] **Step 4: Implement the loop**

Create `src/generator/pipeline/research.py`:

```python
"""Per-section research loop with capped budgets.

Public surface:
- `run_research_stage(sections, canonical_title, facts, seed_sources, budget?)`
  → dict[section_id, list[Source]]
- `ResearchBudget` dataclass (overridable via env vars or kwargs)

The loop runs all sections in parallel under a shared `GlobalBudget` that
tracks total Tavily calls. Per-section, each iteration:
  1. Generate query (or refine using previous gaps)
  2. fetch_tavily(query) → sources
  3. Evaluate pool; if satisfied → exit; else → next iteration

Seed sources (Wikidata + Wikipedia, fetched once at stage start) are
prepended to every section's pool so the eval and the downstream extractor
always see them.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass

from generator.llm.client import call_structured, get_default_model
from generator.prompts.research_query import build_research_query_messages
from generator.pipeline.research_eval import run_research_eval_stage
from generator.schema import (
    EventFacts,
    ResearchEvalResult,
    SectionPlan,
    Source,
)
from generator.sources.tavily import fetch_tavily

DEFAULT_MAX_ITERATIONS_PER_SECTION = 3
DEFAULT_MAX_FETCH_CALLS_PER_SECTION = 4
DEFAULT_MAX_TOTAL_TAVILY = 30


@dataclass
class ResearchBudget:
    max_iterations_per_section: int = DEFAULT_MAX_ITERATIONS_PER_SECTION
    max_fetch_calls_per_section: int = DEFAULT_MAX_FETCH_CALLS_PER_SECTION
    max_total_tavily: int = DEFAULT_MAX_TOTAL_TAVILY

    @classmethod
    def from_env(cls) -> ResearchBudget:
        return cls(
            max_iterations_per_section=int(
                os.getenv("MAX_ITERATIONS_PER_SECTION", DEFAULT_MAX_ITERATIONS_PER_SECTION)
            ),
            max_fetch_calls_per_section=int(
                os.getenv("MAX_FETCH_CALLS_PER_SECTION", DEFAULT_MAX_FETCH_CALLS_PER_SECTION)
            ),
            max_total_tavily=int(
                os.getenv("MAX_TOTAL_TAVILY", DEFAULT_MAX_TOTAL_TAVILY)
            ),
        )


class _GlobalCounter:
    """Async-safe global Tavily call counter."""

    def __init__(self, cap: int) -> None:
        self._cap = cap
        self._used = 0
        self._lock = asyncio.Lock()

    async def reserve(self) -> bool:
        async with self._lock:
            if self._used >= self._cap:
                return False
            self._used += 1
            return True


class _QueryGenInput:
    """Tiny adapter so monkeypatching `_gen_query` is straightforward in tests."""


async def _gen_query(
    *,
    facts: EventFacts | None,
    canonical_title: str,
    section: SectionPlan,
    previous_gaps: list[str] | None,
    previous_query: str | None,
    model: str | None = None,
) -> str:
    """Generate (or refine) one Tavily query via the research-query LLM call."""
    if facts is None:
        # Tests sometimes pass facts=None — fall back to the section intent.
        return section.intent
    messages = build_research_query_messages(
        facts=facts,
        canonical_title=canonical_title,
        section=section,
        previous_gaps=previous_gaps,
        previous_query=previous_query,
    )
    from pydantic import BaseModel, Field

    class _QueryOut(BaseModel):
        query: str = Field(min_length=1, max_length=200)

    resolved = model or get_default_model("research_query")
    out = await call_structured(
        model=resolved, messages=messages, response_model=_QueryOut
    )
    return out.query


async def _section_loop(
    *,
    section: SectionPlan,
    canonical_title: str,
    facts: EventFacts | None,
    seed_sources: list[Source],
    budget: ResearchBudget,
    global_counter: _GlobalCounter,
    primary_entity: str,
) -> list[Source]:
    pool: list[Source] = list(seed_sources)  # always start with seeds
    previous_gaps: list[str] | None = None
    previous_query: str | None = None
    fetch_calls_this_section = 0

    for _ in range(budget.max_iterations_per_section):
        if fetch_calls_this_section >= budget.max_fetch_calls_per_section:
            break
        if not await global_counter.reserve():
            break  # global cap hit; stop trying

        query = await _gen_query(
            facts=facts,
            canonical_title=canonical_title,
            section=section,
            previous_gaps=previous_gaps,
            previous_query=previous_query,
        )
        new_sources = await fetch_tavily(
            query=query,
            time_range_days=14,
            max_results=8,
            primary_entity=primary_entity,
        )
        fetch_calls_this_section += 1

        # Tag with section attribution and merge into pool (dedupe by URL).
        urls_seen = {str(s.url): s for s in pool}
        for s in new_sources:
            tagged = s.model_copy(
                update={"serves_sections": [section.section_id]}
            )
            url_key = str(tagged.url)
            if url_key in urls_seen:
                # Merge serves_sections lists.
                existing = urls_seen[url_key]
                merged = sorted(
                    set(existing.serves_sections) | {section.section_id}
                )
                urls_seen[url_key] = existing.model_copy(
                    update={"serves_sections": merged}
                )
            else:
                urls_seen[url_key] = tagged
        pool = list(urls_seen.values())

        eval_result = await run_research_eval_stage(
            section=section, sources=pool, canonical_title=canonical_title
        )
        if eval_result.satisfied:
            return pool
        previous_gaps = eval_result.gaps
        previous_query = query

    return pool


async def run_research_stage(
    *,
    sections: list[SectionPlan],
    canonical_title: str,
    facts: EventFacts | None,
    seed_sources: list[Source],
    budget: ResearchBudget | None = None,
) -> dict[str, list[Source]]:
    """Run the per-section research loop in parallel under a global budget."""
    b = budget or ResearchBudget.from_env()
    global_counter = _GlobalCounter(b.max_total_tavily)

    primary_entity = facts.entities[0] if facts and facts.entities else ""

    coros = [
        _section_loop(
            section=s,
            canonical_title=canonical_title,
            facts=facts,
            seed_sources=seed_sources,
            budget=b,
            global_counter=global_counter,
            primary_entity=primary_entity,
        )
        for s in sections
    ]
    pools = await asyncio.gather(*coros)
    return {s.section_id: pool for s, pool in zip(sections, pools)}


__all__ = [
    "ResearchBudget",
    "run_research_stage",
    "DEFAULT_MAX_ITERATIONS_PER_SECTION",
    "DEFAULT_MAX_FETCH_CALLS_PER_SECTION",
    "DEFAULT_MAX_TOTAL_TAVILY",
]
```

- [ ] **Step 5:** Run `uv run pytest tests/pipeline/test_research_loop.py -v` — expect PASS (5 tests).

- [ ] **Step 6:** Run `uv run pytest -q` — confirm no regressions.

- [ ] **Step 7: Lint**

Run: `uv run ruff check src/generator/pipeline/research.py tests/pipeline/test_research_loop.py`

- [ ] **Step 8: Commit**

```bash
git add src/generator/pipeline/research.py tests/pipeline/test_research_loop.py tests/fixtures/openrouter_research_query_refine.json
git commit -m "feat(pipeline): per-section research loop with iteration + global budgets"
```

---

## Task 5: Wire research into the CLI flag path

Extend the existing `USE_EDITOR_ARCHITECTURE=1` branch in `cli.py` to also run the research loop (after planners, before exit). Print per-section evidence pool sizes.

**Files:**
- Modify: `src/generator/cli.py` (the existing flag block)

- [ ] **Step 1: Read the current flag block**

Re-read `src/generator/cli.py` from `if os.getenv("USE_EDITOR_ARCHITECTURE") == "1":` through `raise typer.Exit(code=0)`. The block currently prints `combined.model_dump_json(indent=2)` then exits. We need to insert the research stage between the planners and the exit.

- [ ] **Step 2: Update the flag block**

Replace the current `combined = SectionPlanOutput(...); typer.echo(...); raise typer.Exit(...)` with:

```python
            combined = SectionPlanOutput(
                sections=backbone + list(curation_out.sections)
            )

            # Stage 3 (editor): per-section research loop.
            from generator.pipeline.research import run_research_stage
            from generator.sources.wikidata import fetch_wikidata
            from generator.sources.wikipedia import fetch_wikipedia_card

            wd_source, _wd_props = await fetch_wikidata(
                ground_out.facts.entities[0] if ground_out.facts.entities else ""
            )
            _wp_card = await fetch_wikipedia_card(ground_out.canonical_title)
            seed_sources = [wd_source] if wd_source else []

            with recorder.stage("research"):
                pools = await run_research_stage(
                    sections=combined.sections,
                    canonical_title=ground_out.canonical_title,
                    facts=ground_out.facts,
                    seed_sources=seed_sources,
                )

            # Emit a compact summary for the smoke-test path.
            summary = {
                "sections": [
                    {
                        "section_id": s.section_id,
                        "kind": s.kind,
                        "rank": s.rank,
                        "block_kind": s.block_kind,
                        "evidence_count": len(pools.get(s.section_id, [])),
                    }
                    for s in combined.sections
                ],
                "total_sources": sum(len(p) for p in pools.values()),
            }
            typer.echo(json.dumps(summary, indent=2))
            raise typer.Exit(code=0)
```

Note: `json` is already imported in cli.py. `await` is fine because we're inside the existing async `_run()` body.

- [ ] **Step 3:** Run `uv run pytest -q` — full suite passes (existing tests untouched; the integration-test placeholder for the flag path is still skipped).

- [ ] **Step 4: Lint**

Run: `uv run ruff check src/generator/cli.py`

- [ ] **Step 5: Commit**

```bash
git add src/generator/cli.py
git commit -m "feat(cli): wire research loop into USE_EDITOR_ARCHITECTURE path"
```

---

## Task 6: Sanity check

- [ ] **Step 1:** `uv run pytest -q` — all tests pass.
- [ ] **Step 2:** `uv run ruff check .` — clean.
- [ ] **Step 3:** `uv run generate run --help` — unchanged (no new CLI flag).
- [ ] **Step 4:** Final commit only if any fix needed.

---

## What's NOT in Plan 3

- No block extraction (Plan 4).
- No deletion of old `run_fetch_stage` (Plan 5).
- No render changes (Plan 4 will swap render to walk `RenderedSection` lists).
- `Source.serves_sections` is added but the old fetch path doesn't populate it — only the research loop does. The old `serves_needs` keeps working unchanged.

## Acceptance for "Plan 3 done"

- `uv run pytest -q` passes.
- `uv run ruff check .` passes.
- 5 small commits on the feature branch.
- Manual: `USE_EDITOR_ARCHITECTURE=1 uv run generate run --auto "<event>"` prints the per-section evidence summary JSON and exits 0 (optional if API keys not available).
