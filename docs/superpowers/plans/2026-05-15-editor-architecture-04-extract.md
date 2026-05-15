# Editor Architecture — Plan 4: Block-Driven Extraction + Render

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `Module`-driven extraction with `BlockSpec`-driven extraction. Each `SectionPlan` + its per-section evidence pool produces a `RenderedSection`. Render adapts to walk `list[RenderedSection]` when present. Behind `USE_EDITOR_ARCHITECTURE=1`; legacy module path stays default until Plan 5.

**Architecture:** One extractor function per call, dispatching per `block_kind` to the matching `BlockSpec` schema and prompt fragment. A `RenderedSection` carries the `block_data` (already a `RenderBlock`) — no `module_to_block` adapter needed.

**Design decision (locked):** Extend `EventPage` with an optional `editorial_sections: list[RenderedSection] | None = None`. Render dispatches: if `editorial_sections` is set, render that path; otherwise legacy modules path. Plan 5 removes the conditional + the legacy fields.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, asyncio, respx, Jinja2.

---

## File map

**Create:**
- `src/generator/pipeline/block_extract.py`
- `src/generator/prompts/block_extract.py`
- `tests/pipeline/test_block_extract.py`
- `tests/integration/test_editor_render.py`
- `tests/fixtures/openrouter_block_paragraph_happy.json`
- `tests/fixtures/openrouter_block_timeline_happy.json`

**Modify:**
- `src/generator/schema.py` — add `editorial_sections` to `EventPage`; relax `block_data: Any` validation by narrowing to `RenderBlock | None` (use forward-ref or post-init rewire)
- `src/generator/llm/client.py` — add `block_extract` stage fallback
- `src/generator/pipeline/render.py` — `build_editorial_page()` constructor + `render_html` dispatch
- `templates/needs/section.html` — make fact/opinion chip conditional on `section.category` presence
- `src/generator/cli.py` — extend `USE_EDITOR_ARCHITECTURE` branch through extract + render + write artifacts

---

## Task 1: Schema — add `editorial_sections` + tighten `RenderedSection.block_data`

The `RenderedSection.block_data: Any` from Plan 1 was a placeholder. Now we need real validation. We also extend `EventPage`.

**Files:**
- Modify: `src/generator/schema.py`
- Test: `tests/schema/test_editorial_page.py`

- [ ] **Step 1: Write the failing test**

Create `tests/schema/test_editorial_page.py`:

```python
"""EventPage with editorial_sections + RenderedSection validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from generator.blocks.schema import ParagraphBlockData, TimelineBlockData
from generator.schema import EventPage, RenderedSection


def test_event_page_editorial_sections_default_is_none():
    """Existing pipeline path must not have to supply editorial_sections."""
    # We don't construct a full EventPage here — too many required fields.
    # Instead validate the field's default is None via the model schema.
    schema = EventPage.model_json_schema()
    assert "editorial_sections" in schema["properties"]
    field = schema["properties"]["editorial_sections"]
    # default null (Optional[list[RenderedSection]])
    assert field.get("default", None) is None


def test_rendered_section_accepts_paragraph_block_data():
    block = ParagraphBlockData(paragraphs_md=["Hello world."])
    rs = RenderedSection(
        section_id="overview",
        block_kind="paragraph",
        block_data=block,
    )
    assert rs.block_data.kind == "paragraph"


def test_rendered_section_accepts_timeline_block_data():
    block = TimelineBlockData(entries=[])
    rs = RenderedSection(
        section_id="timeline",
        block_kind="timeline",
        block_data=block,
    )
    assert rs.block_data.kind == "timeline"


def test_rendered_section_block_kind_must_match_block_data_kind():
    """If section claims block_kind=paragraph but block_data is TimelineBlockData,
    that's a contract violation. Validate it raises."""
    with pytest.raises(ValidationError):
        RenderedSection(
            section_id="x",
            block_kind="paragraph",
            block_data=TimelineBlockData(entries=[]),
        )
```

- [ ] **Step 2:** Run pytest — expect FAIL (current schema accepts mismatched kinds because block_data is Any; editorial_sections field doesn't exist).

- [ ] **Step 3: Tighten `RenderedSection.block_data` and add `editorial_sections`**

In `src/generator/schema.py`:

a. Find the `RenderedSection` class. Replace the `block_data: Any` field declaration with:

```python
    block_data: "RenderBlock" = Field(...)
```

…and add an import or forward-ref resolution at the bottom of the file:

```python
# Forward-ref resolution (RenderBlock is in generator.blocks.schema which imports from this file)
from generator.blocks.schema import RenderBlock as _RenderBlock  # noqa: E402

RenderedSection.model_rebuild(_types_namespace={"RenderBlock": _RenderBlock})
```

If pydantic v2 doesn't accept that idiom, use the `model_rebuild` pattern at module bottom AFTER all forward refs are defined, or simply set `block_data: _RenderBlock` directly (deferred-import inside a `TYPE_CHECKING` block plus a runtime resolution).

b. Add a `@model_validator(mode="after")` to `RenderedSection`:

```python
    @model_validator(mode="after")
    def _block_kind_matches_data(self) -> "RenderedSection":
        if self.block_data.kind != self.block_kind:
            raise ValueError(
                f"block_kind={self.block_kind} but block_data.kind={self.block_data.kind}"
            )
        return self
```

c. Find the `EventPage` class (around line 499). Add a new optional field:

```python
    editorial_sections: list[RenderedSection] | None = None
```

- [ ] **Step 4:** Run pytest — expect 4 tests pass.

- [ ] **Step 5:** Run `uv run pytest -q` — confirm no regressions (existing render tests still pass because the new field defaults to None).

- [ ] **Step 6: Commit**

```bash
git add src/generator/schema.py tests/schema/test_editorial_page.py
git commit -m "feat(schema): EventPage.editorial_sections + RenderedSection.block_data typed"
```

---

## Task 2: Block-extract prompt builder

**Files:**
- Create: `src/generator/prompts/block_extract.py`
- Test: `tests/prompts/test_block_extract_prompt.py`

- [ ] **Step 1: Write the failing test**

Create `tests/prompts/test_block_extract_prompt.py`:

```python
"""Block-extract prompt builder — composes spec fragment + section context + evidence."""

from __future__ import annotations

from generator.blocks.specs import get_spec
from generator.prompts.block_extract import build_block_extract_messages
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    SectionPlan,
    Source,
    SourceRights,
)


def _section(block_kind: str = "paragraph") -> SectionPlan:
    return SectionPlan(
        section_id="overview",
        kind="backbone",
        title="Overview",
        rank=1,
        block_kind=block_kind,  # type: ignore[arg-type]
        intent="two paragraphs framing the event",
        acceptance=AcceptanceCriteria(description="who/what/when covered"),
    )


def _sources() -> list[Source]:
    return [
        Source(
            id="s1",
            url="https://reuters.com/a",
            publisher=Publisher(name="Reuters", tier="T1"),
            title="t",
            published_at="2026-03-19T12:00:00Z",
            fetched_at="2026-03-19T13:00:00Z",
            language="en",
            rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
            summary="Reuters reports on NVIDIA's GTC keynote.",
        )
    ]


def test_returns_system_and_user_messages():
    msgs = build_block_extract_messages(
        section=_section(),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="NVIDIA GTC 2026",
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_system_message_contains_spec_extraction_fragment():
    msgs = build_block_extract_messages(
        section=_section("paragraph"),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="t",
    )
    system = msgs[0]["content"]
    # The spec's fragment must be embedded.
    assert "paragraphs_md" in system


def test_user_message_includes_evidence_pool_and_intent():
    msgs = build_block_extract_messages(
        section=_section(),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="NVIDIA GTC 2026",
    )
    user = msgs[1]["content"]
    assert "NVIDIA GTC 2026" in user
    assert "s1" in user  # source id present in evidence block
    assert "two paragraphs framing the event" in user  # section intent
    assert "who/what/when covered" in user  # acceptance description


def test_each_block_kind_uses_its_own_fragment():
    """Sanity: changing block_kind changes the system message."""
    p_sys = build_block_extract_messages(
        section=_section("paragraph"),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="t",
    )[0]["content"]
    t_sys = build_block_extract_messages(
        section=_section("timeline"),
        spec=get_spec("timeline"),
        sources=_sources(),
        canonical_title="t",
    )[0]["content"]
    assert p_sys != t_sys
```

```bash
mkdir -p tests/prompts
touch tests/prompts/__init__.py
```

- [ ] **Step 2:** Run pytest — expect FAIL (ModuleNotFoundError).

- [ ] **Step 3: Implement**

Create `src/generator/prompts/block_extract.py`:

```python
"""Prompt builder for the block-extract LLM call.

For each SectionPlan, we compose:
  BASE_PREAMBLE + spec.extraction_prompt_fragment + section context + evidence

The model's response_format is `spec.data_schema` (a Pydantic block-data
class). The CLI-side stage post-validates citations against the per-section
evidence pool.
"""

from __future__ import annotations

from generator.blocks.specs.base import BlockSpec
from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import SectionPlan, Source


def _format_evidence_block(sources: list[Source]) -> str:
    if not sources:
        return "(no evidence)"
    lines = []
    for s in sources:
        line = (
            f"<src id=\"{s.id}\" tier=\"{s.publisher.tier}\" "
            f"publisher=\"{s.publisher.name}\" "
            f"url=\"{s.url}\" published=\"{s.published_at}\">\n"
            f"  title: {s.title}\n"
            f"  summary: {(s.summary or '')[:480]}\n"
            f"</src>"
        )
        lines.append(line)
    return "\n".join(lines)


def build_block_extract_messages(
    *,
    section: SectionPlan,
    spec: type[BlockSpec],
    sources: list[Source],
    canonical_title: str,
) -> list[dict]:
    evidence_block = _format_evidence_block(sources)
    user = (
        f"CANONICAL_TITLE: {canonical_title}\n"
        f"SECTION_ID: {section.section_id}\n"
        f"SECTION_TITLE: {section.title}\n"
        f"INTENT: {section.intent}\n"
        f"ACCEPTANCE: {section.acceptance.description}\n"
        f"BLOCK_KIND: {section.block_kind}\n"
        f"\n<evidence>\n{evidence_block}\n</evidence>\n"
        f"\nOUTPUT a {section.block_kind} block JSON now."
    )
    return [
        {
            "role": "system",
            "content": (
                BASE_PREAMBLE + "\n\n" + spec.extraction_prompt_fragment
            ),
        },
        {"role": "user", "content": user},
    ]


__all__ = ["build_block_extract_messages"]
```

- [ ] **Step 4:** Run pytest — expect 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/generator/prompts/block_extract.py tests/prompts/test_block_extract_prompt.py tests/prompts/__init__.py
git commit -m "feat(prompts): block-extract prompt builder"
```

---

## Task 3: Block-extract stage

**Files:**
- Create: `src/generator/pipeline/block_extract.py`
- Test: `tests/pipeline/test_block_extract.py`
- Test fixtures: `tests/fixtures/openrouter_block_paragraph_happy.json`, `tests/fixtures/openrouter_block_timeline_happy.json`
- Modify: `src/generator/llm/client.py` — add `"block_extract": "anthropic/claude-haiku-4-5"` to `_STAGE_FALLBACK_MODELS`

- [ ] **Step 1: Add the canned fixtures**

`tests/fixtures/openrouter_block_paragraph_happy.json`:
```json
{
  "id": "x",
  "object": "chat.completion",
  "model": "anthropic/claude-haiku-4-5",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"kind\":\"paragraph\",\"style\":\"prose\",\"paragraphs_md\":[\"NVIDIA opened GTC 2026 with a keynote in San Jose.\",\"The new GPU was the headline.\"],\"pull_quotes\":[],\"citations\":[{\"source_id\":\"s1\"}]}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 400, "completion_tokens": 60, "total_tokens": 460}
}
```

`tests/fixtures/openrouter_block_timeline_happy.json`:
```json
{
  "id": "x",
  "object": "chat.completion",
  "model": "anthropic/claude-haiku-4-5",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "{\"kind\":\"timeline\",\"entries\":[{\"title\":\"Announcement\",\"time\":\"2026-02-01\",\"importance\":\"feature\",\"source_id\":\"s1\"},{\"title\":\"Keynote\",\"time\":\"2026-03-19\",\"importance\":\"breaking\",\"source_id\":\"s1\"},{\"title\":\"Press follow-up\",\"time\":\"2026-03-20\",\"importance\":\"normal\",\"source_id\":\"s1\"}]}"
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {"prompt_tokens": 400, "completion_tokens": 80, "total_tokens": 480}
}
```

- [ ] **Step 2: Write the failing test**

Create `tests/pipeline/test_block_extract.py`:

```python
"""Block-extract stage: one LLM call per section, returning RenderedSection."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
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
```

- [ ] **Step 3:** Run pytest — expect FAIL (ModuleNotFoundError).

- [ ] **Step 4: Register the new stage model**

In `src/generator/llm/client.py`, add to `_STAGE_FALLBACK_MODELS`:

```python
"block_extract": "anthropic/claude-haiku-4-5",
```

- [ ] **Step 5: Implement the stage**

Create `src/generator/pipeline/block_extract.py`:

```python
"""Block-driven extraction: one RenderedSection per SectionPlan.

Replaces the legacy Module-driven extract.py for the editor-architecture
path. Per-section:
  1. Lookup BlockSpec by block_kind.
  2. Compose prompt: BASE_PREAMBLE + spec.extraction_prompt_fragment + section
     context + evidence block.
  3. LLM call with response_model = spec.data_schema.
  4. Post-validate citations against the evidence pool. Drop section if any
     cited source_id is unknown.
  5. Apply spec.is_minimum_viable(); drop if False.
  6. Return RenderedSection(section_id, block_kind, block_data, citations,
     sources_used, eval_passed=True).
"""

from __future__ import annotations

import asyncio
import logging

from generator.blocks.specs import get_spec
from generator.llm.client import call_structured, get_default_model
from generator.prompts.block_extract import build_block_extract_messages
from generator.schema import (
    Citation,
    RenderedSection,
    SectionPlan,
    Source,
)

logger = logging.getLogger(__name__)


def _collect_cited_ids(obj) -> set[str]:
    """Recursive walker — find every source_id reference in a block_data tree."""
    cited: set[str] = set()
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source_id" and isinstance(v, str):
                cited.add(v)
            else:
                cited |= _collect_cited_ids(v)
    elif isinstance(obj, list):
        for item in obj:
            cited |= _collect_cited_ids(item)
    return cited


async def extract_one_section(
    *,
    section: SectionPlan,
    sources: list[Source],
    canonical_title: str,
    model: str | None = None,
) -> RenderedSection | None:
    spec_cls = get_spec(section.block_kind)
    spec = spec_cls()
    messages = build_block_extract_messages(
        section=section,
        spec=spec_cls,
        sources=sources,
        canonical_title=canonical_title,
    )
    resolved_model = model or get_default_model("block_extract")
    try:
        data = await call_structured(
            model=resolved_model,
            messages=messages,
            response_model=spec.data_schema,
        )
    except Exception as exc:
        logger.warning("block_extract failed for %s: %s", section.section_id, exc)
        return None

    # Citation integrity: every cited source_id must be in the pool.
    pool_ids = {s.id for s in sources}
    cited_ids = _collect_cited_ids(data)
    unknown = cited_ids - pool_ids
    if unknown:
        logger.warning(
            "block_extract dropped %s: cites unknown source_ids %s",
            section.section_id,
            unknown,
        )
        return None

    if not spec.is_minimum_viable(data):
        logger.info(
            "block_extract dropped %s: is_minimum_viable=False", section.section_id
        )
        return None

    citations = [Citation(source_id=cid) for cid in sorted(cited_ids)]
    sources_used = [s for s in sources if s.id in cited_ids]

    return RenderedSection(
        section_id=section.section_id,
        block_kind=section.block_kind,
        block_data=data,
        citations=citations,
        sources_used=sources_used,
        eval_passed=True,
        eval_notes=None,
    )


async def run_block_extract_stage(
    *,
    sections: list[SectionPlan],
    evidence_by_section: dict[str, list[Source]],
    canonical_title: str,
) -> list[RenderedSection]:
    """Extract all sections in parallel. Dropped sections are filtered out."""
    coros = [
        extract_one_section(
            section=s,
            sources=evidence_by_section.get(s.section_id, []),
            canonical_title=canonical_title,
        )
        for s in sections
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)
    out: list[RenderedSection] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("block_extract task raised: %s", r)
            continue
        if r is not None:
            out.append(r)
    return out


__all__ = ["extract_one_section", "run_block_extract_stage"]
```

- [ ] **Step 6:** Run pytest — expect all 5 tests pass.

- [ ] **Step 7:** Run `uv run pytest -q` — confirm no regressions.

- [ ] **Step 8: Commit**

```bash
git add src/generator/llm/client.py src/generator/pipeline/block_extract.py tests/pipeline/test_block_extract.py tests/fixtures/openrouter_block_paragraph_happy.json tests/fixtures/openrouter_block_timeline_happy.json
git commit -m "feat(pipeline): block-driven extract stage producing RenderedSections"
```

---

## Task 4: Render adaptation

Adapt `render.build_page` to optionally accept `editorial_sections` and produce an `EventPage` whose render path walks them. Add a `_build_editorial_sections()` helper that mirrors `_build_sections()` in shape (so `templates/needs/section.html` can be reused).

**Files:**
- Modify: `src/generator/pipeline/render.py`
- Modify: `templates/needs/section.html` — fact/opinion chip conditional
- Test: `tests/pipeline/test_render_editorial.py`

- [ ] **Step 1: Write the failing test**

Create `tests/pipeline/test_render_editorial.py`:

```python
"""Render walks editorial_sections when present."""

from __future__ import annotations

from datetime import datetime, timezone

from generator.blocks.schema import (
    NewsCard,
    NewsfeedBlockData,
    ParagraphBlockData,
)
from generator.pipeline.render import build_editorial_page, render_html
from generator.schema import (
    EventLayout,
    EventMeta,
    EventSubject,
    Publisher,
    RenderedSection,
    Source,
    SourceRights,
)


def _src() -> Source:
    return Source(
        id="s1",
        url="https://reuters.com/a",
        publisher=Publisher(name="Reuters", tier="T1"),
        title="t",
        published_at="2026-03-19T12:00:00Z",
        fetched_at="2026-03-19T13:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )


def _subject() -> EventSubject:
    return EventSubject(
        title="NVIDIA GTC 2026",
        entities=["NVIDIA"],
        when="2026-03-19T12:00:00Z",
        where="San Jose",
    )


def _layout() -> EventLayout:
    return EventLayout(preset_id="product_focus", overrides=None)


def _meta() -> EventMeta:
    return EventMeta(
        canonical_title="NVIDIA GTC 2026",
        slug="nvidia-gtc-2026",
        confidence_overall=0.9,
    )


def test_editorial_page_renders_two_sections():
    sections = [
        RenderedSection(
            section_id="overview",
            block_kind="paragraph",
            block_data=ParagraphBlockData(paragraphs_md=["NVIDIA held its keynote."]),
        ),
        RenderedSection(
            section_id="media_coverage",
            block_kind="newsfeed",
            block_data=NewsfeedBlockData(
                cards=[
                    NewsCard(
                        url="https://reuters.com/a",
                        title="t",
                        publisher="Reuters",
                        tier="T1",
                    ),
                    NewsCard(
                        url="https://reuters.com/b",
                        title="t2",
                        publisher="Reuters",
                        tier="T1",
                    ),
                ]
            ),
        ),
    ]
    page = build_editorial_page(
        input_sentence="x",
        page_id="p1",
        subject=_subject(),
        layout=_layout(),
        sources=[_src()],
        editorial_sections=sections,
        trace_id="trace_x",
        meta=_meta(),
    )
    assert page.editorial_sections == sections
    assert page.modules == []  # editorial path has no modules

    html = render_html(page)
    assert "NVIDIA held its keynote." in html
    assert 'id="section-overview"' in html
    assert 'id="section-media_coverage"' in html


def test_render_html_legacy_path_still_works_when_editorial_sections_none():
    """Sanity: existing render tests use editorial_sections=None and must still pass."""
    # This is covered by the existing tests/integration/test_render_two_column.py
    # — we re-run it implicitly when `uv run pytest -q` runs.
    pass
```

- [ ] **Step 2:** Run pytest — expect FAIL (ImportError for `build_editorial_page`).

- [ ] **Step 3: Add `build_editorial_page` + render dispatch**

In `src/generator/pipeline/render.py`:

a. Add a new constructor function next to `build_page`:

```python
def build_editorial_page(
    *,
    input_sentence: str,
    page_id: str,
    subject: EventSubject,
    layout: EventLayout,
    sources: list[Source],
    editorial_sections: list[RenderedSection],
    trace_id: str,
    meta: EventMeta,
    wikipedia_card: WikipediaCardData | None = None,
) -> EventPage:
    """Construct an EventPage that uses the editorial render path."""
    return EventPage(
        page_id=page_id,
        input_sentence=input_sentence,
        generated_at=datetime.now(timezone.utc).isoformat(),
        subject=subject,
        modules=[],  # editorial path: no modules
        layout=layout,
        sources=sources,
        needs_coverage={},
        uncovered_needs=[],
        need_plans=[],
        wikipedia_card=wikipedia_card,
        editorial_sections=editorial_sections,
        meta=meta,
    )
```

b. Add a `_build_editorial_section_dicts()` helper:

```python
def _build_editorial_section_dicts(
    editorial: list[RenderedSection],
) -> list[dict]:
    out = []
    for idx, rs in enumerate(editorial, start=1):
        out.append({
            "need_id": rs.section_id,           # template reuses need_id for id="section-..."
            "section_id": rs.section_id,
            "title": rs.section_id.replace("_", " ").title(),
            "category": None,                   # no fact/opinion chip in editorial path
            "blocks": [rs.block_data],
            "section_index": idx,
        })
    return out
```

c. Inside `render_html()`, before the existing `sections = _build_sections(page)` call, dispatch:

```python
def render_html(page: EventPage) -> str:
    env = Environment(loader=FileSystemLoader(_TEMPLATES_DIR), autoescape=True)
    ...
    if page.editorial_sections is not None:
        sections = _build_editorial_section_dicts(page.editorial_sections)
    else:
        sections = _build_sections(page)
    ...
```

(Refactor the existing body — keep the legacy code path exactly the same, just gate it on `page.editorial_sections is None`.)

- [ ] **Step 4: Adapt the `templates/needs/section.html` to handle missing category**

Read the current `templates/needs/section.html`. Find the `{% if section.category == "opinion" %}` block. Wrap the entire eyebrow chip block in:

```jinja2
{% if section.category %}
  <div class="need-section__eyebrow">
    <span class="need-section__chip">
      {%- if section.category == "opinion" -%}Opinion
      {%- else -%}Fact
      {%- endif -%}
    </span>
  </div>
{% endif %}
```

Also change the section id from `id="need-{{ section.need_id }}"` to `id="section-{{ section.section_id | default(section.need_id) }}"` so both old and new paths produce stable ids.

(If the section id is referenced from JS / CSS elsewhere, do `id="section-{{ section.section_id | default(section.need_id) }}"` to support both; that's the only safe change.)

- [ ] **Step 5:** Run pytest — the new render test should pass; existing render tests must still pass (the chip block was wrapped in a conditional, so it still renders when `section.category` is truthy).

- [ ] **Step 6:** Commit:

```bash
git add src/generator/pipeline/render.py templates/needs/section.html tests/pipeline/test_render_editorial.py
git commit -m "feat(render): editorial render path walks RenderedSection list"
```

---

## Task 5: Wire extract + render into CLI flag path

Extend the `USE_EDITOR_ARCHITECTURE=1` branch to: planners → research → extract → render → write artifacts → exit.

**Files:**
- Modify: `src/generator/cli.py`

- [ ] **Step 1: Read current flag block**

The current flag block (after Plan 3) ends by printing a summary JSON and `raise typer.Exit(code=0)`. Replace that summary-print + exit with the full extract + render + write flow.

- [ ] **Step 2: Update the flag block**

Replace the summary echo + exit with:

```python
            # Stage 4 (editor): block-driven extraction.
            from generator.pipeline.block_extract import run_block_extract_stage
            with recorder.stage("block_extract"):
                rendered_sections = await run_block_extract_stage(
                    sections=combined.sections,
                    evidence_by_section=pools,
                    canonical_title=ground_out.canonical_title,
                )
            console.print(
                f"[green]✓[/green] Block extract  sections={len(rendered_sections)}"
            )

            # Stage 6 (editor): render.
            from generator.pipeline.render import (
                build_editorial_page,
                render_html,
                slugify,
                subject_from_facts,
            )
            from generator.schema import EventLayout, EventMeta

            subject_e = subject_from_facts(
                ground_out.facts, ground_out.canonical_title
            )
            all_sources = list({s.id: s for pool in pools.values() for s in pool}.values())

            with recorder.stage("render"):
                editorial_page = build_editorial_page(
                    input_sentence=sentence,
                    page_id=page_id,
                    subject=subject_e,
                    layout=EventLayout(preset_id="product_focus", overrides=None),
                    sources=all_sources + seed_sources,
                    editorial_sections=rendered_sections,
                    trace_id=recorder.trace_id,
                    meta=EventMeta(
                        canonical_title=ground_out.canonical_title,
                        slug=slugify(ground_out.canonical_title),
                        confidence_overall=ground_out.confidence,
                    ),
                    wikipedia_card=_wp_card,
                )
                html = render_html(editorial_page)

            # Stage 7 (editor): deliver.
            slug = slugify(ground_out.canonical_title)
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            (_OUTPUT_DIR / f"{slug}.html").write_text(html, encoding="utf-8")
            (_OUTPUT_DIR / f"{slug}.data.json").write_text(
                editorial_page.model_dump_json(indent=2), encoding="utf-8"
            )
            console.print(
                f"[green]✓[/green] Wrote {slug}.html and {slug}.data.json"
            )
            raise typer.Exit(code=0)
```

(Read the legacy delivery block in cli.py to confirm `_OUTPUT_DIR` usage and `slug` derivation; copy the trace.json write if it's easy to factor out, otherwise skip trace write on the editor path — Plan 5 will unify it.)

- [ ] **Step 3:** Run `uv run pytest -q` — all tests pass.

- [ ] **Step 4: Lint**

`uv run ruff check src/generator/cli.py`

- [ ] **Step 5: Commit**

```bash
git add src/generator/cli.py
git commit -m "feat(cli): USE_EDITOR_ARCHITECTURE path renders + writes editorial page"
```

---

## Task 6: End-to-end integration test for editor path

Wire up the placeholder skipped test from Plan 2.

**Files:**
- Modify: `tests/integration/test_editor_architecture_flag.py`
- Possibly create new fixtures.

- [ ] **Step 1:** Read the existing `tests/integration/test_end_to_end.py` to see how it patches LLM + HTTP calls, builds a `Typer.testing.CliRunner` invocation, and asserts on output files. Mirror that pattern.

- [ ] **Step 2:** Replace the `pytest.skip("Placeholder...")` body with a full test that:
  - Sets env `USE_EDITOR_ARCHITECTURE=1`
  - Patches all LLM endpoints (ground, curation, research_query, research_eval, block_extract) with canned fixtures (some new, some reusing existing).
  - Patches `fetch_tavily` and `fetch_wikidata` and `fetch_wikipedia_card` to return canned shapes.
  - Invokes the CLI with `--auto` on a sample sentence.
  - Asserts: exit code 0, an output `.html` file exists, contains expected section ids.

If creating all the canned fixtures is too much, narrow the test to validate the CLI path can be invoked and exits 0 with mocks returning empty sources / minimal data, then mark `xfail` any HTML assertions that depend on richer fixtures. The point is to verify the wiring, not full output quality.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_editor_architecture_flag.py tests/fixtures/
git commit -m "test(integration): end-to-end USE_EDITOR_ARCHITECTURE smoke test"
```

---

## Task 7: Sanity check

- [ ] **Step 1:** `uv run pytest -q` — all tests pass.
- [ ] **Step 2:** `uv run ruff check .` — clean.
- [ ] **Step 3:** Existing `test_render_two_column.py` still green (legacy path untouched).
- [ ] **Step 4:** Final commit only if any fix needed.

---

## What's NOT in Plan 4

- No deletions (`Module`, `extract.py`, `converter.py`, legacy schemas) — Plan 5.
- No CLI rename (`regen-module` → `regen-section`) — Plan 5.
- No flag flip — Plan 5.
- The editor path's HTML output is functional, not pixel-parity with the legacy path. Quality parity check is part of Plan 5's spot-check acceptance criteria.

## Acceptance for "Plan 4 done"

- `uv run pytest -q` passes.
- `uv run ruff check .` passes.
- `USE_EDITOR_ARCHITECTURE=1 uv run generate run --auto "<event>"` produces an HTML page and a data.json (manual, optional if no API keys).
- Existing render tests are untouched.
