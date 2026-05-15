# Editor Architecture — Plan 2: Backbone + Curation Planners

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the two-stage `run_plan_stage` + `run_aesthetic_stage` with an editorial planner that emits `SectionPlanOutput` (introduced in Plan 1). Gated behind `USE_EDITOR_ARCHITECTURE=1` env var so old pipeline keeps running by default.

**Architecture:** Two planners — `backbone_planner` (deterministic, 0 LLM calls, emits 6 backbone sections) and `curation_planner` (one LLM call, emits 0–4 curated sections). CLI flag-gates a new code path that runs `ground → backbone + curation → exits cleanly`, printing `SectionPlanOutput` JSON. Fetch/extract/render stay on the old path until Plans 3–4.

**Tech Stack:** Python 3.12, Pydantic v2, pytest (`asyncio_mode=auto`), uv, ruff, respx.

---

## Why behind a flag

The new planner emits a different output shape (`SectionPlanOutput` vs. `NeedPlanOutput` + `AestheticPlanOutput`) that the existing fetch/extract/render stages can't consume yet. The env flag lets us land the new control flow as a dead-end smoke-test path (run + inspect SectionPlanOutput JSON) without touching the live pipeline. Plans 3–4 fill in the rest of the path behind the same flag; Plan 5 flips the default.

## File map

**Create:**
- `src/generator/pipeline/backbone_planner.py` — deterministic 6-section emitter
- `src/generator/pipeline/curation_planner.py` — one LLM call → curated sections
- `src/generator/prompts/curation.py` — prompt for the curation planner

**Modify:**
- `src/generator/llm/client.py` — add `"curation"` to `_STAGE_FALLBACK_MODELS`
- `src/generator/cli.py` — env-flag branch after ground stage; print SectionPlanOutput; exit 0

**Test:**
- `tests/pipeline/test_backbone_planner.py`
- `tests/pipeline/test_curation_planner.py`
- `tests/integration/test_editor_architecture_flag.py`
- `tests/fixtures/openrouter_curation_happy.json` (canned LLM response)

---

## Task 1: Backbone planner (deterministic)

**Files:**
- Create: `src/generator/pipeline/backbone_planner.py`
- Test: `tests/pipeline/test_backbone_planner.py`

The backbone planner is pure data: 6 always-on sections, pre-filled `title`, `intent`, and `default_acceptance` pulled from each section's `BlockSpec`. Zero LLM cost, deterministic, instantly testable.

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_backbone_planner.py`:

```python
"""Backbone planner: deterministic 6-section emitter."""

from __future__ import annotations

from generator.pipeline.backbone_planner import build_backbone_sections
from generator.schema import EventFacts


def _facts() -> EventFacts:
    return EventFacts(
        entities=["NVIDIA", "GTC 2026"],
        what="NVIDIA announces new GPU architecture at GTC.",
        when="2026-03-19T14:00:00-07:00",
        where="San Jose, CA",
        why="Generation leap in AI compute capacity.",
        supporting_sources=["s1"],
    )


def test_emits_six_backbone_sections_in_canonical_order():
    sections = build_backbone_sections(_facts(), canonical_title="NVIDIA GTC 2026")
    ids = [s.section_id for s in sections]
    assert ids == [
        "overview",
        "key_takeaways",
        "timeline",
        "key_facts",
        "background",
        "media_coverage",
    ]


def test_each_section_is_kind_backbone_with_unique_rank():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    assert all(s.kind == "backbone" for s in sections)
    ranks = [s.rank for s in sections]
    assert ranks == [1, 2, 3, 4, 5, 6]


def test_block_kind_mapping_matches_design():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    by_id = {s.section_id: s for s in sections}
    assert by_id["overview"].block_kind == "paragraph"
    assert by_id["key_takeaways"].block_kind == "paragraph"
    assert by_id["timeline"].block_kind == "timeline"
    assert by_id["key_facts"].block_kind == "factsheet"
    assert by_id["background"].block_kind == "paragraph"
    assert by_id["media_coverage"].block_kind == "newsfeed"


def test_each_section_has_nonempty_title_and_intent():
    sections = build_backbone_sections(_facts(), canonical_title="t")
    for s in sections:
        assert s.title.strip(), f"empty title on {s.section_id}"
        assert s.intent.strip(), f"empty intent on {s.section_id}"


def test_acceptance_pulled_from_blockspec_default():
    from generator.blocks.specs import get_spec

    sections = build_backbone_sections(_facts(), canonical_title="t")
    for s in sections:
        spec_cls = get_spec(s.block_kind)
        # Backbone planner copies the spec's default_acceptance unless the
        # section needs a stricter variant. At minimum, description matches.
        assert s.acceptance.description == spec_cls.default_acceptance.description


def test_title_incorporates_canonical_title_for_overview():
    sections = build_backbone_sections(_facts(), canonical_title="NVIDIA GTC 2026")
    overview = next(s for s in sections if s.section_id == "overview")
    # Overview's intent should reference the event by canonical title.
    assert "NVIDIA GTC 2026" in overview.intent
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipeline/test_backbone_planner.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'generator.pipeline.backbone_planner'`.

- [ ] **Step 3: Implement the planner**

Create `src/generator/pipeline/backbone_planner.py`:

```python
"""Backbone planner — deterministic 6-section emitter.

Zero LLM calls. Maps the 6 always-on backbone section IDs to canonical
titles, intents, block kinds, and ranks. Acceptance criteria default to the
matching BlockSpec's `default_acceptance` so the research loop (Plan 3) has
something to measure against.

If a section needs stricter acceptance than the spec default, build a new
AcceptanceCriteria here — never mutate spec defaults.
"""

from __future__ import annotations

from generator.blocks.specs import get_spec
from generator.schema import (
    AcceptanceCriteria,
    BackboneSectionId,
    BlockKind,
    EventFacts,
    SectionPlan,
)

# Canonical ordering. Rank assigned by position in this list.
_BACKBONE_ORDER: tuple[BackboneSectionId, ...] = (
    "overview",
    "key_takeaways",
    "timeline",
    "key_facts",
    "background",
    "media_coverage",
)

_BLOCK_KIND_FOR_ID: dict[BackboneSectionId, BlockKind] = {
    "overview": "paragraph",
    "key_takeaways": "paragraph",
    "timeline": "timeline",
    "key_facts": "factsheet",
    "background": "paragraph",
    "media_coverage": "newsfeed",
}

_TITLES: dict[BackboneSectionId, str] = {
    "overview": "Overview",
    "key_takeaways": "Key takeaways",
    "timeline": "Timeline",
    "key_facts": "Key facts",
    "background": "Background",
    "media_coverage": "Media coverage",
}


def _intent_for(section_id: BackboneSectionId, canonical_title: str) -> str:
    return {
        "overview": (
            f"Two short paragraphs introducing {canonical_title}: what just "
            f"happened, who is involved, when/where, and why a reader should care."
        ),
        "key_takeaways": (
            "Three to five tight bullets surfacing the most consequential facts. "
            "Each bullet is a standalone claim — no narrative."
        ),
        "timeline": (
            "Three to seven milestone entries tracing the event arc from earliest "
            "verifiable trigger to the most recent development."
        ),
        "key_facts": (
            "Labeled key/value facts (date, location, principals, headline numbers). "
            "Skip rows where the value is unknown."
        ),
        "background": (
            "Two paragraphs of context the reader needs to understand why this event "
            "matters — prior history, structural setup, or the slow build-up."
        ),
        "media_coverage": (
            "Three to eight high-signal external articles from distinct publishers, "
            "biased toward T0/T1 outlets, ordered by recency."
        ),
    }[section_id]


def build_backbone_sections(
    facts: EventFacts, canonical_title: str
) -> list[SectionPlan]:
    """Return the 6 always-on backbone sections in canonical rank order."""
    sections: list[SectionPlan] = []
    for rank, section_id in enumerate(_BACKBONE_ORDER, start=1):
        block_kind = _BLOCK_KIND_FOR_ID[section_id]
        spec_cls = get_spec(block_kind)
        acceptance: AcceptanceCriteria = spec_cls.default_acceptance
        sections.append(
            SectionPlan(
                section_id=section_id,
                kind="backbone",
                title=_TITLES[section_id],
                rank=rank,
                block_kind=block_kind,
                intent=_intent_for(section_id, canonical_title),
                acceptance=acceptance,
            )
        )
    return sections


__all__ = ["build_backbone_sections"]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/pipeline/test_backbone_planner.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Lint**

Run: `uv run ruff check src/generator/pipeline/backbone_planner.py tests/pipeline/test_backbone_planner.py`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/generator/pipeline/backbone_planner.py tests/pipeline/test_backbone_planner.py
git commit -m "feat(pipeline): deterministic backbone planner emitting 6 sections"
```

---

## Task 2: Curation prompt + model registration

The curation planner is a single LLM call. We need (a) a prompt module and (b) `"curation"` registered in the per-stage model fallback dict so `get_default_model("curation")` works.

**Files:**
- Modify: `src/generator/llm/client.py:33-39` — add curation fallback
- Create: `src/generator/prompts/curation.py`
- Test: `tests/pipeline/test_curation_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_curation_prompt.py`:

```python
"""Curation prompt builder."""

from __future__ import annotations

from generator.prompts.curation import build_curation_messages
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


def _backbone() -> list[SectionPlan]:
    return [
        SectionPlan(
            section_id="overview",
            kind="backbone",
            title="Overview",
            rank=1,
            block_kind="paragraph",
            intent="i",
            acceptance=AcceptanceCriteria(description="d"),
        )
    ]


def test_returns_system_and_user_messages():
    msgs = build_curation_messages(
        facts=_facts(), canonical_title="NVIDIA GTC 2026", backbone=_backbone()
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_system_message_lists_seven_block_kinds():
    msgs = build_curation_messages(
        facts=_facts(), canonical_title="t", backbone=_backbone()
    )
    system = msgs[0]["content"]
    for kind in [
        "paragraph", "timeline", "chart", "newsfeed",
        "factsheet", "map", "reactions",
    ]:
        assert kind in system, f"block kind {kind} missing from prompt"


def test_user_payload_includes_facts_and_already_chosen_sections():
    msgs = build_curation_messages(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        backbone=_backbone(),
    )
    user = msgs[1]["content"]
    assert "NVIDIA GTC 2026" in user
    assert "overview" in user  # already-chosen section listed


def test_system_message_bounds_curated_count_zero_to_four():
    msgs = build_curation_messages(
        facts=_facts(), canonical_title="t", backbone=_backbone()
    )
    system = msgs[0]["content"]
    # The prompt must state the allowed count range so the LLM can't run away.
    assert "0" in system and "4" in system
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/pipeline/test_curation_prompt.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 3: Add curation to model fallback dict**

Edit `src/generator/llm/client.py`. In `_STAGE_FALLBACK_MODELS` (lines 33-39), add a `"curation"` entry:

```python
_STAGE_FALLBACK_MODELS = {
    "ground": "anthropic/claude-sonnet-4-6",
    "plan": "anthropic/claude-sonnet-4-6",
    "curation": "anthropic/claude-sonnet-4-6",
    "aesthetic": "anthropic/claude-haiku-4-5",
    "extract": "anthropic/claude-haiku-4-5",
    "consistency": "anthropic/claude-haiku-4-5",
}
```

- [ ] **Step 4: Implement the prompt module**

Create `src/generator/prompts/curation.py`:

```python
"""Prompt builder for the curation planner.

One LLM call. Input: triage facts + canonical title + the 6 backbone sections
already chosen. Output: 0–4 SectionPlan objects with `kind="curated"`.

The curation planner is a one-shot — there is no refinement loop. It picks
the few extra sections that make THIS specific event richer than the generic
backbone alone could.
"""

from __future__ import annotations

import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import EventFacts, SectionPlan

_BLOCK_KIND_CATALOG = """\
Block kinds you can choose for each curated section (closed enum):

- paragraph: prose or bullet text. Use for narrative, analysis, explainer.
- timeline: ordered milestone entries. Use only if NOT already covered by the backbone timeline.
- chart: stat callouts, bar series, or compare tables. Use for quantitative payloads.
- newsfeed: external link cards. Use for "where to watch", "channels", "quote roundup".
- factsheet: labeled key/value rows. Use for cast lists, lineups, KPI tables.
- map: geocoded locations. Use only when geography is load-bearing.
- reactions: 2–4 quote cards spanning multiple sentiments or stakeholder tiers.
"""

_INSTRUCTIONS = """\
You are the curation planner. The backbone planner has already chosen six
always-on sections (listed under "ALREADY CHOSEN"). Your job: decide which
0 to 4 additional sections would make THIS event meaningfully richer.

Rules:
1. Output between 0 and 4 curated sections. Fewer is fine. Zero is fine.
2. Never duplicate or paraphrase a backbone section. If `overview` already
   covers context, don't add another paragraph called "Context".
3. Each curated section must pass a "would the reader miss it?" test. If you
   can't articulate the unique value in one sentence, skip it.
4. `section_id` is a free-form snake_case slug (e.g. "kpi_dashboard",
   "people_relationships", "where_to_watch"). It must NOT collide with any
   BackboneSectionId.
5. `kind` must be `"curated"`.
6. `rank` starts at 7 (after the 6 backbone ranks) and increments. No gaps.
7. `block_kind` must be one of the 7 closed-enum kinds above.
8. `intent`: one sentence describing what the section answers and how.
9. `acceptance.description`: one sentence describing what success looks like.
   Set `min_sources` and `min_publishers` honestly — a niche curated section
   often needs only 1 source, a reactions block needs ≥2 distinct sentiments.

Triage hints for picking sections:
- Sports / live event: consider "where_to_watch" (newsfeed variant=channels)
  or a "lineup" (factsheet).
- Product launch / earnings: consider "kpi_dashboard" (chart, stat or bar).
- Geopolitical / disaster: consider a map.
- Polarizing / contested: consider a reactions section spanning sentiments.
- Comparative (rival product, prior cycle): consider a chart compare_table.

Strict output: a SectionPlanOutput JSON object with a `sections` list (0–4
items). Do NOT include the backbone sections in your output — only your
additions.
"""


def build_curation_messages(
    facts: EventFacts,
    canonical_title: str,
    backbone: list[SectionPlan],
) -> list[dict]:
    already_chosen = [
        {
            "section_id": s.section_id,
            "title": s.title,
            "block_kind": s.block_kind,
            "intent": s.intent,
        }
        for s in backbone
    ]
    user_payload = {
        "canonical_title": canonical_title,
        "entities": facts.entities,
        "what": facts.what,
        "when": facts.when,
        "where": facts.where,
        "why": facts.why,
        "already_chosen": already_chosen,
    }
    return [
        {
            "role": "system",
            "content": (
                BASE_PREAMBLE
                + "\n\n"
                + _BLOCK_KIND_CATALOG
                + "\n"
                + _INSTRUCTIONS
            ),
        },
        {
            "role": "user",
            "content": (
                "Curate 0–4 additional sections for the following event.\n\n"
                + json.dumps(user_payload, indent=2)
                + "\n\nOUTPUT a SectionPlanOutput now."
            ),
        },
    ]


__all__ = ["build_curation_messages"]
```

- [ ] **Step 5: Run tests**

Run: `uv run pytest tests/pipeline/test_curation_prompt.py -v`
Expected: PASS, 4 tests.

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/generator/llm/client.py src/generator/prompts/curation.py tests/pipeline/test_curation_prompt.py`
Expected: clean.

- [ ] **Step 7: Commit**

```bash
git add src/generator/llm/client.py src/generator/prompts/curation.py tests/pipeline/test_curation_prompt.py
git commit -m "feat(prompts): add curation planner prompt + register curation stage model"
```

---

## Task 3: Curation planner stage

**Files:**
- Create: `src/generator/pipeline/curation_planner.py`
- Create: `tests/fixtures/openrouter_curation_happy.json` (canned LLM response)
- Test: `tests/pipeline/test_curation_planner.py`

- [ ] **Step 1: Add the canned response fixture**

Create `tests/fixtures/openrouter_curation_happy.json` with a minimal valid SectionPlanOutput wrapped in an OpenRouter response envelope. Look at `tests/fixtures/openrouter_plan_happy.json` for the envelope shape and adapt — at minimum:

```json
{
  "id": "chatcmpl-fake-curation",
  "object": "chat.completion",
  "model": "anthropic/claude-sonnet-4-6",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"sections\":[{\"section_id\":\"where_to_watch\",\"kind\":\"curated\",\"title\":\"Where to watch\",\"rank\":7,\"block_kind\":\"newsfeed\",\"intent\":\"Stream and broadcast options for the keynote.\",\"acceptance\":{\"description\":\"At least 3 channels.\",\"min_sources\":1,\"min_publishers\":1,\"required_facets\":[],\"forbid_single_perspective\":false}}]}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 200, "completion_tokens": 80, "total_tokens": 280}
}
```

(Copy the envelope verbatim from `openrouter_plan_happy.json` — do not invent fields the existing client doesn't expect.)

- [ ] **Step 2: Write the failing test**

Create `tests/pipeline/test_curation_planner.py`:

```python
"""Curation planner stage — one LLM call producing 0-4 curated SectionPlans."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx

from generator.llm.trace_buffer import reset
from generator.pipeline.curation_planner import run_curation_stage
from generator.schema import (
    AcceptanceCriteria,
    EventFacts,
    SectionPlan,
    SectionPlanOutput,
)

FIX = Path(__file__).parent.parent / "fixtures"


def _facts() -> EventFacts:
    return EventFacts(
        entities=["NVIDIA"],
        what="GTC 2026 keynote",
        when="2026-03-19",
        where="San Jose",
        why="New architecture",
        supporting_sources=["s1"],
    )


def _backbone() -> list[SectionPlan]:
    return [
        SectionPlan(
            section_id="overview",
            kind="backbone",
            title="Overview",
            rank=1,
            block_kind="paragraph",
            intent="i",
            acceptance=AcceptanceCriteria(description="d"),
        )
    ]


@respx.mock
async def test_curation_stage_returns_section_plan_output(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_curation_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    out = await run_curation_stage(
        facts=_facts(),
        canonical_title="NVIDIA GTC 2026",
        backbone=_backbone(),
    )
    assert isinstance(out, SectionPlanOutput)
    assert all(s.kind == "curated" for s in out.sections)


@respx.mock
async def test_curation_stage_records_llm_call(monkeypatch):
    from generator.llm.trace_buffer import drain

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    payload = json.loads((FIX / "openrouter_curation_happy.json").read_text())
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=payload)
    )
    await run_curation_stage(
        facts=_facts(), canonical_title="t", backbone=_backbone()
    )
    calls = drain()
    assert len(calls) == 1
    assert calls[0].stage == "curation"


async def test_curation_stage_returns_empty_when_llm_returns_empty(monkeypatch):
    """An LLM that says "no curated sections needed" must produce an empty
    SectionPlanOutput, not a crash."""
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")
    reset()
    empty_envelope = {
        "id": "x",
        "object": "chat.completion",
        "model": "anthropic/claude-sonnet-4-6",
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": "{\"sections\":[]}"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105},
    }
    with respx.mock:
        respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=empty_envelope)
        )
        out = await run_curation_stage(
            facts=_facts(), canonical_title="t", backbone=_backbone()
        )
    assert out.sections == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/pipeline/test_curation_planner.py -v`
Expected: FAIL with ModuleNotFoundError.

- [ ] **Step 4: Implement the stage**

Create `src/generator/pipeline/curation_planner.py`:

```python
"""Curation planner — one LLM call producing 0-4 curated SectionPlans.

Stage name: "curation". Model fallback: anthropic/claude-sonnet-4-6
(override via MODEL_CURATION env var).

The LLM is constrained to a SectionPlanOutput schema with `kind="curated"`
on every entry. Validation enforces this contract; bad output raises
LLMOutputError which the CLI maps to exit code 4.
"""

from __future__ import annotations

from generator.llm.client import call_structured, get_default_model
from generator.llm.trace_buffer import set_stage_for_pending_calls
from generator.prompts.curation import build_curation_messages
from generator.schema import EventFacts, SectionPlan, SectionPlanOutput


async def run_curation_stage(
    facts: EventFacts,
    canonical_title: str,
    backbone: list[SectionPlan],
    *,
    model: str | None = None,
) -> SectionPlanOutput:
    """One LLM call. Returns 0-4 curated sections to complement the backbone.

    Backbone sections must NOT appear in the output. Caller is responsible
    for combining `backbone + curation_output.sections` before downstream
    stages consume them.
    """
    resolved_model = model or get_default_model("curation")
    messages = build_curation_messages(
        facts=facts, canonical_title=canonical_title, backbone=backbone
    )
    set_stage_for_pending_calls("curation")
    return await call_structured(
        model=resolved_model,
        messages=messages,
        response_model=SectionPlanOutput,
    )


__all__ = ["run_curation_stage"]
```

**IMPORTANT:** If `set_stage_for_pending_calls` does not exist in `generator.llm.trace_buffer`, fall back to whatever idiom the existing planner uses. Read `src/generator/pipeline/plan.py` to confirm how the stage name attaches to an `LLMCall`. If the existing code attaches stage via context (e.g., via `TraceRecorder.stage(...)` only), drop the `set_stage_for_pending_calls` line — the CLI's `with recorder.stage("curation"):` wrapper will handle it.

Also: if the test `test_curation_stage_records_llm_call` checks `calls[0].stage == "curation"` and the stage name actually comes from the trace recorder (not from inside the call), update that assertion to check what's available (e.g., `calls[0].model == "anthropic/claude-sonnet-4-6"`).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/pipeline/test_curation_planner.py -v`
Expected: PASS, 3 tests. If the stage-name assertion fails because of how `LLMCall.stage` is wired, adjust the test (not the implementation) — the existing planner's test is the reference.

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/generator/pipeline/curation_planner.py tests/pipeline/test_curation_planner.py`

- [ ] **Step 7: Commit**

```bash
git add src/generator/pipeline/curation_planner.py tests/pipeline/test_curation_planner.py tests/fixtures/openrouter_curation_happy.json
git commit -m "feat(pipeline): curation planner stage with LLM-driven curated sections"
```

---

## Task 4: CLI feature-flag branch

When `USE_EDITOR_ARCHITECTURE=1`, the CLI runs `ground → backbone + curation → print SectionPlanOutput JSON → exit 0`. The old code path is the default; the new path is purely additive.

**Files:**
- Modify: `src/generator/cli.py` — insert flag branch after the ground stage (before old `run_plan_stage` invocation)
- Test: `tests/integration/test_editor_architecture_flag.py`

- [ ] **Step 1: Read the current `cli.py` ground → plan transition**

Read `src/generator/cli.py:60-145` so you know exactly where ground ends and Stage 2 begins. The flag branch must:
- Sit AFTER the ground stage completes (so `ground_out.facts` is available)
- Sit AFTER any HITL `ground_review` prompt (so editor-edited facts are respected)
- Run BEFORE `run_plan_stage`
- Exit cleanly with code 0 after printing — do not fall through to old code

- [ ] **Step 2: Write the failing integration test**

Create `tests/integration/test_editor_architecture_flag.py`:

```python
"""When USE_EDITOR_ARCHITECTURE=1, the CLI runs the new planners and exits."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.mark.skipif(
    not (FIX / "openrouter_ground_happy.json").exists(),
    reason="needs the ground fixture used by the main e2e test",
)
def test_editor_architecture_flag_prints_section_plan(tmp_path, monkeypatch):
    """The end-to-end here is heavy; the cheap variant lives in the unit tests.
    This test only verifies the CLI honours the flag and exits with code 0
    after printing a SectionPlanOutput-shaped payload.
    """
    # The body of this test should reuse the same respx + monkeypatch shape
    # as tests/integration/test_end_to_end.py. If that test imports a
    # `_invoke_cli` helper or uses Typer's CliRunner, copy the pattern.
    pytest.skip(
        "Placeholder — wire up like test_end_to_end.py once that helper is "
        "factored out. Filed as a follow-up."
    )
```

- [ ] **Step 3: Implement the flag branch in `cli.py`**

The exact insertion point depends on the current line numbers (research showed Stage 2 starts at line 108). Insert after the ground stage's HITL prompt resolves and before `run_plan_stage` is called. Pseudocode:

```python
# ... ground stage already done, facts available as `ground_out.facts` ...

if os.getenv("USE_EDITOR_ARCHITECTURE") == "1":
    from generator.pipeline.backbone_planner import build_backbone_sections
    from generator.pipeline.curation_planner import run_curation_stage
    from generator.schema import SectionPlanOutput

    backbone = build_backbone_sections(
        ground_out.facts, canonical_title=ground_out.canonical_title
    )
    with recorder.stage("curation"):
        curation_out = await run_curation_stage(
            facts=ground_out.facts,
            canonical_title=ground_out.canonical_title,
            backbone=backbone,
        )

    combined = SectionPlanOutput(
        sections=backbone + list(curation_out.sections)
    )
    typer.echo(combined.model_dump_json(indent=2))
    raise typer.Exit(code=0)

# old path continues here (unchanged): run_plan_stage, run_aesthetic_stage, ...
```

Implementation notes:
- The new imports go inside the `if` block to avoid loading curation code on the default path.
- `os` is already imported in `cli.py`; if not, add it.
- Use `typer.echo` (already used elsewhere in cli.py) to emit the JSON.
- The `recorder.stage("curation")` context manager handles trace recording AND drains LLM calls into the stage — that's the canonical pattern, matching what the old `with recorder.stage("plan"):` does at line 109.
- If `ground_out.canonical_title` could be `None` for any edge case where the flag is on but the title wasn't generated, fall back to `ground_out.facts.what[:80]`.

- [ ] **Step 4: Run all tests**

Run: `uv run pytest -q`
Expected: All pre-existing tests still pass. The new placeholder test should be skipped.

Run: `USE_EDITOR_ARCHITECTURE=1 uv run generate run --auto "NVIDIA announced new GPU at GTC 2026 keynote"` (manual smoke test) — should exit 0 and print a SectionPlanOutput JSON.

If you don't have an OPENROUTER_API_KEY available in CI, skip the manual smoke test and rely on the unit tests.

- [ ] **Step 5: Lint and format**

Run: `uv run ruff check src/generator/ tests/`
Run: `uv run ruff format src/generator/cli.py`

- [ ] **Step 6: Commit**

```bash
git add src/generator/cli.py tests/integration/test_editor_architecture_flag.py
git commit -m "feat(cli): USE_EDITOR_ARCHITECTURE flag runs new planners and exits"
```

---

## Task 5: Sanity check — old pipeline still default

This task does not write new code. It confirms Plan 2's flag is off by default.

- [ ] **Step 1: Run full test suite without the flag**

Run: `uv run pytest -q`
Expected: All tests pass.

- [ ] **Step 2: Confirm the help output is unchanged**

Run: `uv run generate run --help`
Expected: same flags as before; no `--editor-architecture` flag exposed (flag is env-var only by design — keeps CLI surface small).

- [ ] **Step 3: Final commit (only if any incidental fixes were needed)**

If steps 1-2 surfaced a problem, fix and commit; otherwise skip.

---

## What's NOT in Plan 2

- No research loop (Plan 3) — the new path stops after planning.
- No block extraction (Plan 4) — `SectionPlanOutput` is printed, not rendered.
- No `Module` deletions (Plan 5).
- No CLI surface flag — env var only, on purpose.

## Acceptance for "Plan 2 done"

- `uv run pytest -q` passes.
- `uv run ruff check .` passes.
- `git log --oneline` shows 4 small commits on the feature branch.
- Manual: `USE_EDITOR_ARCHITECTURE=1 uv run generate run --auto "<event>"` exits 0 with valid SectionPlanOutput JSON on stdout (optional if no API key handy).
