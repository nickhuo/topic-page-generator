# Editor Architecture — Plan 1: Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `BlockSpec` registry and `SectionPlan` schema types as purely additive code — old pipeline keeps running unchanged.

**Architecture:** New `src/generator/blocks/specs/` subpackage holds one file per `BlockKind`, each declaring its `data_schema`, `extraction_prompt_fragment`, `is_minimum_viable` check, and default acceptance criteria. New section types (`SectionPlan`, `RenderedSection`, `AcceptanceCriteria`, `BackboneSectionId`) get added to `src/generator/schema.py`. Nothing is wired into the pipeline yet.

**Tech Stack:** Python 3.12, Pydantic v2, pytest (`asyncio_mode=auto`), uv, ruff.

---

## Why "purely additive"

Old `Module` ABC, `NeedCurationPlan`, `converter.py`, and all pipeline stages stay untouched. The new types and BlockSpecs sit alongside, fully tested in isolation. Plan 2 will start *using* them. This lets us land Plan 1 with zero risk to the running pipeline.

## File map

**Create:**
- `src/generator/schema.py` — append new types (do not split; `schema.py` is single source of truth per CLAUDE.md)
- `src/generator/blocks/specs/__init__.py` — registry
- `src/generator/blocks/specs/base.py` — `BlockSpec` ABC
- `src/generator/blocks/specs/paragraph.py`
- `src/generator/blocks/specs/timeline.py`
- `src/generator/blocks/specs/chart.py`
- `src/generator/blocks/specs/factsheet.py`
- `src/generator/blocks/specs/newsfeed.py`
- `src/generator/blocks/specs/map.py`
- `src/generator/blocks/specs/reactions.py`

**Modify:**
- `src/generator/blocks/schema.py` — add `style: Literal["prose", "bullets"]` field to `ParagraphBlockData`

**Test:**
- `tests/schema/test_section_types.py`
- `tests/blocks/specs/test_registry.py`
- `tests/blocks/specs/test_paragraph_spec.py`
- `tests/blocks/specs/test_timeline_spec.py`
- `tests/blocks/specs/test_chart_spec.py`
- `tests/blocks/specs/test_factsheet_spec.py`
- `tests/blocks/specs/test_newsfeed_spec.py`
- `tests/blocks/specs/test_map_spec.py`
- `tests/blocks/specs/test_reactions_spec.py`

---

## Task 1: Add section schema primitives

**Files:**
- Modify: `src/generator/schema.py` (append after the existing `BlockKind` block, around line 560)
- Test: `tests/schema/test_section_types.py`

- [ ] **Step 1: Write the failing test**

Create `tests/schema/test_section_types.py`:

```python
"""Tests for the new section-level schema primitives."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from generator.schema import (
    AcceptanceCriteria,
    BackboneSectionId,
    SectionPlan,
    SectionPlanOutput,
    RenderedSection,
)
from generator.blocks.schema import ParagraphBlockData


def test_backbone_section_id_is_closed_enum():
    valid = {
        "overview",
        "key_takeaways",
        "timeline",
        "background",
        "key_facts",
        "media_coverage",
    }
    # Construct one of each via SectionPlan to confirm Literal acceptance.
    for sid in valid:
        sp = SectionPlan(
            section_id=sid,
            kind="backbone",
            title="t",
            rank=1,
            block_kind="paragraph",
            intent="i",
            acceptance=AcceptanceCriteria(description="d"),
        )
        assert sp.section_id == sid


def test_acceptance_criteria_defaults():
    a = AcceptanceCriteria(description="cover who/what/when")
    assert a.min_sources == 1
    assert a.min_publishers == 1
    assert a.required_facets == []


def test_section_plan_curated_requires_string_section_id():
    sp = SectionPlan(
        section_id="people_relationships",
        kind="curated",
        title="Key people",
        rank=5,
        block_kind="factsheet",
        intent="who is involved and how",
        acceptance=AcceptanceCriteria(description="≥3 people"),
    )
    assert sp.kind == "curated"
    assert sp.section_id == "people_relationships"


def test_section_plan_rejects_unknown_block_kind():
    with pytest.raises(ValidationError):
        SectionPlan(
            section_id="overview",
            kind="backbone",
            title="t",
            rank=1,
            block_kind="not_a_real_kind",  # type: ignore[arg-type]
            intent="i",
            acceptance=AcceptanceCriteria(description="d"),
        )


def test_section_plan_output_orders_by_rank_field_not_position():
    out = SectionPlanOutput(
        sections=[
            SectionPlan(
                section_id="background",
                kind="backbone",
                title="b",
                rank=4,
                block_kind="paragraph",
                intent="i",
                acceptance=AcceptanceCriteria(description="d"),
            ),
            SectionPlan(
                section_id="overview",
                kind="backbone",
                title="o",
                rank=1,
                block_kind="paragraph",
                intent="i",
                acceptance=AcceptanceCriteria(description="d"),
            ),
        ]
    )
    # Order is preserved as given; the rank field is what consumers sort by.
    assert [s.section_id for s in out.sections] == ["background", "overview"]
    assert [s.rank for s in out.sections] == [4, 1]


def test_rendered_section_round_trip():
    block = ParagraphBlockData(paragraphs_md=["Hello."])
    rs = RenderedSection(
        section_id="overview",
        block_kind="paragraph",
        block_data=block,
        citations=[],
        sources_used=[],
        eval_passed=True,
        eval_notes=None,
    )
    assert rs.block_data.paragraphs_md == ["Hello."]
    assert rs.eval_passed is True
```

Also create the directory marker:
```bash
mkdir -p tests/schema
touch tests/schema/__init__.py
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/schema/test_section_types.py -v`
Expected: FAIL with `ImportError: cannot import name 'AcceptanceCriteria' from 'generator.schema'`

- [ ] **Step 3: Add the new types to `schema.py`**

Append to `src/generator/schema.py` after the `BlockKind = Literal[...]` declaration (current line 559). Insert before the `FetchAngle` block:

```python
# ---------------------------------------------------------------------------
# Editor-architecture section types (Plan 1 foundation, not yet wired).
# ---------------------------------------------------------------------------
BackboneSectionId = Literal[
    "overview",
    "key_takeaways",
    "timeline",
    "background",
    "key_facts",
    "media_coverage",
]

SectionKind = Literal["backbone", "curated"]


class AcceptanceCriteria(_Frozen):
    """What the research loop must achieve before a section is considered done."""

    description: str
    min_sources: int = 1
    min_publishers: int = 1
    required_facets: list[str] = Field(default_factory=list)
    forbid_single_perspective: bool = False


class SectionPlan(_Frozen):
    """One section to render on the page — produced by the editorial planner.

    `section_id` is a BackboneSectionId literal when `kind="backbone"`, and a
    free-form snake_case string for curated sections (e.g. "people_relationships",
    "kpi_dashboard"). Validation is deferred to the planner stage.
    """

    section_id: str
    kind: SectionKind
    title: str
    rank: int = Field(ge=1, le=20)
    block_kind: BlockKind
    intent: str
    acceptance: AcceptanceCriteria


class SectionPlanOutput(_Frozen):
    """Combined output of backbone + curation planners."""

    sections: list[SectionPlan]


class RenderedSection(_Frozen):
    """A fully extracted section, ready for the renderer.

    Replaces what TypedModule carried in the old architecture: block data,
    citations, source attribution, and the section's eval outcome. Confidence
    is computed at render time from `sources_used`, not stored here.
    """

    section_id: str
    block_kind: BlockKind
    block_data: Any  # discriminated RenderBlock; kept Any to avoid forward-ref cycle
    citations: list["Citation"] = Field(default_factory=list)
    sources_used: list["Source"] = Field(default_factory=list)
    eval_passed: bool = True
    eval_notes: str | None = None
```

**Important:** the `Any` for `block_data` is intentional — `RenderBlock` is defined in `blocks/schema.py`, which already imports from `generator.schema`. Pointing the other way would create a cycle. Plan 2's planner code will cast at the boundary.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/schema/test_section_types.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 5: Run full test suite to confirm no regressions**

Run: `uv run pytest -q`
Expected: All pre-existing tests still pass.

- [ ] **Step 6: Lint**

Run: `uv run ruff check src/generator/schema.py tests/schema/`
Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/generator/schema.py tests/schema/
git commit -m "feat(schema): add SectionPlan / AcceptanceCriteria / RenderedSection types"
```

---

## Task 2: Add `style` variant to `ParagraphBlockData`

The backbone section `key_takeaways` needs a bullets variant. Add it now so all later BlockSpec tests can reference it.

**Files:**
- Modify: `src/generator/blocks/schema.py:117-122`
- Test: `tests/blocks/test_paragraph_style.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/test_paragraph_style.py`:

```python
from generator.blocks.schema import ParagraphBlockData


def test_paragraph_style_defaults_to_prose():
    p = ParagraphBlockData(paragraphs_md=["x"])
    assert p.style == "prose"


def test_paragraph_style_bullets():
    p = ParagraphBlockData(paragraphs_md=["one", "two"], style="bullets")
    assert p.style == "bullets"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/test_paragraph_style.py -v`
Expected: FAIL with `AttributeError: ... 'style'` or pydantic extra-forbid error.

- [ ] **Step 3: Add the field**

Edit `src/generator/blocks/schema.py`, change the `ParagraphBlockData` class (currently lines 117-122) to:

```python
class ParagraphBlockData(_Frozen):
    kind: Literal["paragraph"] = "paragraph"
    style: Literal["prose", "bullets"] = "prose"
    paragraphs_md: list[str] = Field(min_length=1)
    pull_quotes: list[PullQuote] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/test_paragraph_style.py tests/test_render.py -v`
Expected: new tests PASS, render tests still PASS (default value keeps existing fixtures valid).

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/schema.py tests/blocks/test_paragraph_style.py
git commit -m "feat(blocks): add ParagraphBlockData.style for prose vs bullets"
```

---

## Task 3: `BlockSpec` ABC

**Files:**
- Create: `src/generator/blocks/specs/__init__.py` (empty registry shim for now)
- Create: `src/generator/blocks/specs/base.py`
- Test: `tests/blocks/specs/test_base.py`

- [ ] **Step 1: Write the failing test**

```bash
mkdir -p tests/blocks/specs
touch tests/blocks/specs/__init__.py
```

Create `tests/blocks/specs/test_base.py`:

```python
"""BlockSpec ABC contract test."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


def test_blockspec_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BlockSpec()  # type: ignore[abstract]


def test_blockspec_subclass_must_declare_required_classvars():
    class Incomplete(BlockSpec):
        pass

    with pytest.raises(AttributeError):
        Incomplete.kind  # accessing missing ClassVar


def test_blockspec_subclass_with_classvars_instantiates():
    class _Dummy(BaseModel):
        text: str

    class _DummySpec(BlockSpec):
        kind = "paragraph"
        data_schema = _Dummy
        template_path = "blocks/paragraph.html"
        extraction_prompt_fragment = "fragment"
        default_acceptance = AcceptanceCriteria(description="d")

        def is_minimum_viable(self, data):
            return bool(data.text)

    spec = _DummySpec()
    assert spec.kind == "paragraph"
    assert spec.is_minimum_viable(_Dummy(text="x")) is True
    assert spec.is_minimum_viable(_Dummy(text="")) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_base.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'generator.blocks.specs'`.

- [ ] **Step 3: Create the `specs/__init__.py` stub**

Create `src/generator/blocks/specs/__init__.py`:

```python
"""BlockSpec registry. Per-kind specs live in sibling modules.

The registry is populated lazily by importing each spec module (which
registers itself via `BlockSpec.__init_subclass__`). Task 11 wires up
get_spec(); for now this file is a placeholder.
"""

from __future__ import annotations

from generator.blocks.specs.base import BlockSpec

__all__ = ["BlockSpec"]
```

- [ ] **Step 4: Create `base.py`**

Create `src/generator/blocks/specs/base.py`:

```python
"""BlockSpec ABC — one per BlockKind. Owns extraction + render + eval contracts.

Each concrete spec declares the data shape it consumes, a prompt fragment
that explains that shape to the LLM, a render template path, and a check
that decides whether extracted data is worth rendering at all.

Section-specific intent and acceptance criteria are injected at runtime by
the planner — they are NOT baked into the spec.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from generator.schema import AcceptanceCriteria, BlockKind


class BlockSpec(ABC):
    kind: ClassVar[BlockKind]
    data_schema: ClassVar[type[BaseModel]]
    template_path: ClassVar[str]
    extraction_prompt_fragment: ClassVar[str]
    default_acceptance: ClassVar[AcceptanceCriteria]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Late import to avoid circular dependency with __init__.py.
        from generator.blocks.specs import _REGISTRY

        if "kind" in cls.__dict__:
            _REGISTRY[cls.kind] = cls

    @abstractmethod
    def is_minimum_viable(self, data: BaseModel) -> bool:
        """Return False to drop a section whose extracted data is too thin."""
```

- [ ] **Step 5: Add `_REGISTRY` to `specs/__init__.py`**

Update `src/generator/blocks/specs/__init__.py`:

```python
"""BlockSpec registry. Per-kind specs live in sibling modules.

The registry is populated lazily by importing each spec module (which
registers itself via `BlockSpec.__init_subclass__`). Task 11 wires up
get_spec() and the eager-import of all specs.
"""

from __future__ import annotations

from generator.blocks.specs.base import BlockSpec
from generator.schema import BlockKind

_REGISTRY: dict[BlockKind, type[BlockSpec]] = {}

__all__ = ["BlockSpec", "_REGISTRY"]
```

- [ ] **Step 6: Run tests**

Run: `uv run pytest tests/blocks/specs/test_base.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 7: Commit**

```bash
git add src/generator/blocks/specs/ tests/blocks/specs/test_base.py tests/blocks/specs/__init__.py
git commit -m "feat(blocks): introduce BlockSpec ABC and empty registry"
```

---

## Task 4: `ParagraphBlockSpec`

**Files:**
- Create: `src/generator/blocks/specs/paragraph.py`
- Test: `tests/blocks/specs/test_paragraph_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_paragraph_spec.py`:

```python
from generator.blocks.schema import ParagraphBlockData
from generator.blocks.specs.paragraph import ParagraphBlockSpec


def test_paragraph_spec_metadata():
    spec = ParagraphBlockSpec()
    assert spec.kind == "paragraph"
    assert spec.data_schema is ParagraphBlockData
    assert spec.template_path == "blocks/paragraph.html"
    assert "paragraphs_md" in spec.extraction_prompt_fragment


def test_paragraph_minimum_viable_empty_fails():
    spec = ParagraphBlockSpec()
    # Pydantic enforces min_length=1, but a constructed-then-blanked instance
    # would slip through; the spec must still reject all-empty paragraphs.
    data = ParagraphBlockData(paragraphs_md=["   "])
    assert spec.is_minimum_viable(data) is False


def test_paragraph_minimum_viable_ok():
    spec = ParagraphBlockSpec()
    data = ParagraphBlockData(paragraphs_md=["A real sentence."])
    assert spec.is_minimum_viable(data) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_paragraph_spec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement the spec**

Create `src/generator/blocks/specs/paragraph.py`:

```python
"""Paragraph block spec — prose or bullet lists."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import ParagraphBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class ParagraphBlockSpec(BlockSpec):
    kind: ClassVar = "paragraph"
    data_schema: ClassVar = ParagraphBlockData
    template_path: ClassVar = "blocks/paragraph.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least one well-cited paragraph or three bullets.",
        min_sources=2,
        min_publishers=2,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `paragraph` block.

Schema:
- style: "prose" for flowing paragraphs, "bullets" for a tight list.
- paragraphs_md: 1-4 markdown strings. For prose, each is a paragraph (60-140 words).
  For bullets, each is one bullet line (<=24 words, no leading dash).
- pull_quotes: optional 0-2 stand-out quotes from the evidence.
- citations: cite every factual claim via source_id.
"""

    def is_minimum_viable(self, data: ParagraphBlockData) -> bool:
        return any(p.strip() for p in data.paragraphs_md)
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/test_paragraph_spec.py -v`
Expected: PASS, 3 tests.

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/specs/paragraph.py tests/blocks/specs/test_paragraph_spec.py
git commit -m "feat(blocks): ParagraphBlockSpec"
```

---

## Task 5: `TimelineBlockSpec`

**Files:**
- Create: `src/generator/blocks/specs/timeline.py`
- Test: `tests/blocks/specs/test_timeline_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_timeline_spec.py`:

```python
from generator.blocks.schema import TimelineBlockData, TimelineEntry
from generator.blocks.specs.timeline import TimelineBlockSpec


def _entry(title="t") -> TimelineEntry:
    return TimelineEntry(title=title, time="2026-05-15")


def test_timeline_spec_metadata():
    spec = TimelineBlockSpec()
    assert spec.kind == "timeline"
    assert spec.template_path == "blocks/timeline.html"


def test_timeline_minimum_viable_requires_two_entries():
    spec = TimelineBlockSpec()
    one = TimelineBlockData(entries=[_entry()])
    two = TimelineBlockData(entries=[_entry("a"), _entry("b")])
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(two) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_timeline_spec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/generator/blocks/specs/timeline.py`:

```python
"""Timeline block spec — ordered, time-tagged events."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import TimelineBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class TimelineBlockSpec(BlockSpec):
    kind: ClassVar = "timeline"
    data_schema: ClassVar = TimelineBlockData
    template_path: ClassVar = "blocks/timeline.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 3 milestone entries spanning the event arc.",
        min_sources=2,
        required_facets=["start", "end_or_latest"],
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `timeline` block.

Schema:
- entries: ordered list of TimelineEntry. Each has:
    - title (<=80 chars, what happened)
    - time (ISO8601 if known, otherwise a human label like "Quarter Finals")
    - location (optional)
    - description (optional, <=160 chars)
    - importance: "breaking" | "feature" | "minor" | "normal"
    - source_id (cite where this entry's facts come from)
- timezone: IANA timezone string if entries have absolute times.

Aim for 3-7 entries. Each must be a milestone, not routine sub-event.
"""

    def is_minimum_viable(self, data: TimelineBlockData) -> bool:
        return len(data.entries) >= 2
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/test_timeline_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/specs/timeline.py tests/blocks/specs/test_timeline_spec.py
git commit -m "feat(blocks): TimelineBlockSpec"
```

---

## Task 6: `ChartBlockSpec`

**Files:**
- Create: `src/generator/blocks/specs/chart.py`
- Test: `tests/blocks/specs/test_chart_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_chart_spec.py`:

```python
from generator.blocks.schema import (
    ChartBlockData,
    ChartStat,
    ChartSeries,
    ComparisonRow,
    ComparisonTable,
)
from generator.blocks.specs.chart import ChartBlockSpec


def test_chart_spec_metadata():
    spec = ChartBlockSpec()
    assert spec.kind == "chart"
    assert spec.template_path == "blocks/chart.html"


def test_chart_stat_minimum_viable():
    spec = ChartBlockSpec()
    empty = ChartBlockData(chart_type="stat", stats=[])
    one = ChartBlockData(
        chart_type="stat",
        stats=[ChartStat(value="42", label="Goals")],
    )
    assert spec.is_minimum_viable(empty) is False
    assert spec.is_minimum_viable(one) is True


def test_chart_bar_minimum_viable_needs_series():
    spec = ChartBlockSpec()
    no_series = ChartBlockData(chart_type="bar")
    with_series = ChartBlockData(
        chart_type="bar", series=[ChartSeries(label="A", values=[1.0, 2.0])]
    )
    assert spec.is_minimum_viable(no_series) is False
    assert spec.is_minimum_viable(with_series) is True


def test_chart_compare_table_minimum_viable():
    spec = ChartBlockSpec()
    empty = ChartBlockData(chart_type="compare_table")
    full = ChartBlockData(
        chart_type="compare_table",
        table=ComparisonTable(
            subjects=["A", "B"], rows=[ComparisonRow(axis="x", cells=["1", "2"])]
        ),
    )
    assert spec.is_minimum_viable(empty) is False
    assert spec.is_minimum_viable(full) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_chart_spec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/generator/blocks/specs/chart.py`:

```python
"""Chart block spec — stat callouts, bar series, or compare tables."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import ChartBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class ChartBlockSpec(BlockSpec):
    kind: ClassVar = "chart"
    data_schema: ClassVar = ChartBlockData
    template_path: ClassVar = "blocks/chart.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least one quantitative payload (stat/series/table).",
        min_sources=1,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `chart` block.

Choose ONE chart_type and fill the matching field:
- "stat": fill `stats` with 1-4 ChartStat (value, unit?, label, comparison?, source_id).
- "bar": fill `series` with 1-3 ChartSeries (label, values, unit?).
- "compare_table": fill `table` with ComparisonTable (subjects, rows).

Only the chosen field is required; leave others null.
Cite every number via source_id.
"""

    def is_minimum_viable(self, data: ChartBlockData) -> bool:
        if data.chart_type == "stat":
            return bool(data.stats)
        if data.chart_type == "bar":
            return bool(data.series)
        if data.chart_type == "compare_table":
            return data.table is not None and bool(data.table.rows)
        return False
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/test_chart_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/specs/chart.py tests/blocks/specs/test_chart_spec.py
git commit -m "feat(blocks): ChartBlockSpec"
```

---

## Task 7: `FactsheetBlockSpec`

**Files:**
- Create: `src/generator/blocks/specs/factsheet.py`
- Test: `tests/blocks/specs/test_factsheet_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_factsheet_spec.py`:

```python
from generator.blocks.schema import FactsheetBlockData, FactsheetRow
from generator.blocks.specs.factsheet import FactsheetBlockSpec


def test_factsheet_spec_metadata():
    spec = FactsheetBlockSpec()
    assert spec.kind == "factsheet"
    assert spec.template_path == "blocks/factsheet.html"


def test_factsheet_minimum_viable_three_rows():
    spec = FactsheetBlockSpec()
    short = FactsheetBlockData(rows=[FactsheetRow(label="x", value="1")])
    full = FactsheetBlockData(
        rows=[
            FactsheetRow(label="a", value="1"),
            FactsheetRow(label="b", value="2"),
            FactsheetRow(label="c", value="3"),
        ]
    )
    assert spec.is_minimum_viable(short) is False
    assert spec.is_minimum_viable(full) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_factsheet_spec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/generator/blocks/specs/factsheet.py`:

```python
"""Factsheet block spec — labeled key/value pairs (infobox-style)."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import FactsheetBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class FactsheetBlockSpec(BlockSpec):
    kind: ClassVar = "factsheet"
    data_schema: ClassVar = FactsheetBlockData
    template_path: ClassVar = "blocks/factsheet.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 3 high-signal labeled facts.",
        min_sources=2,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `factsheet` block.

Schema:
- rows: 3-8 FactsheetRow. Each has:
    - label: short noun phrase (<=24 chars), e.g. "Date", "Location", "CEO".
    - value: a string OR list of strings (for multi-value facts).
    - source_id: cite the row.

Order rows by descending importance. Skip rows where the value is unknown.
"""

    def is_minimum_viable(self, data: FactsheetBlockData) -> bool:
        return len(data.rows) >= 3
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/test_factsheet_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/specs/factsheet.py tests/blocks/specs/test_factsheet_spec.py
git commit -m "feat(blocks): FactsheetBlockSpec"
```

---

## Task 8: `NewsfeedBlockSpec`

**Files:**
- Create: `src/generator/blocks/specs/newsfeed.py`
- Test: `tests/blocks/specs/test_newsfeed_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_newsfeed_spec.py`:

```python
from generator.blocks.schema import NewsfeedBlockData, NewsCard
from generator.blocks.specs.newsfeed import NewsfeedBlockSpec


def _card(url="https://e.example/a") -> NewsCard:
    return NewsCard(url=url, title="t", publisher="P", tier="T1")


def test_newsfeed_spec_metadata():
    spec = NewsfeedBlockSpec()
    assert spec.kind == "newsfeed"
    assert spec.template_path == "blocks/newsfeed.html"


def test_newsfeed_minimum_viable_needs_two_cards():
    spec = NewsfeedBlockSpec()
    one = NewsfeedBlockData(cards=[_card()])
    two = NewsfeedBlockData(
        cards=[_card("https://e.example/a"), _card("https://e.example/b")]
    )
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(two) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_newsfeed_spec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/generator/blocks/specs/newsfeed.py`:

```python
"""Newsfeed block spec — a list of external link cards."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import NewsfeedBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class NewsfeedBlockSpec(BlockSpec):
    kind: ClassVar = "newsfeed"
    data_schema: ClassVar = NewsfeedBlockData
    template_path: ClassVar = "blocks/newsfeed.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 3 cards from distinct publishers.",
        min_sources=3,
        min_publishers=3,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `newsfeed` block.

Schema:
- variant: "news" (default), "channels" (where-to-watch), or "quotes".
- grouping: "by_perspective" | "by_subtopic" | "by_time" | "flat".
- cards: 3-8 NewsCard. Each has url, title, publisher, tier, published_at?,
  thumbnail_url?, summary?, source_id?.

Pick `variant` + `grouping` to match section intent. Prefer T0/T1 publishers.
Do not repeat the same publisher more than twice.
"""

    def is_minimum_viable(self, data: NewsfeedBlockData) -> bool:
        return len(data.cards) >= 2
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/test_newsfeed_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/specs/newsfeed.py tests/blocks/specs/test_newsfeed_spec.py
git commit -m "feat(blocks): NewsfeedBlockSpec"
```

---

## Task 9: `MapBlockSpec`

**Files:**
- Create: `src/generator/blocks/specs/map.py`
- Test: `tests/blocks/specs/test_map_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_map_spec.py`:

```python
from generator.blocks.schema import Location, MapBlockData
from generator.blocks.specs.map import MapBlockSpec


def test_map_spec_metadata():
    spec = MapBlockSpec()
    assert spec.kind == "map"
    assert spec.template_path == "blocks/map.html"


def test_map_minimum_viable_needs_location_with_coords():
    spec = MapBlockSpec()
    no_coords = MapBlockData(locations=[Location(name="Somewhere")])
    with_coords = MapBlockData(
        locations=[Location(name="Paris", lat=48.85, lon=2.35)]
    )
    assert spec.is_minimum_viable(no_coords) is False
    assert spec.is_minimum_viable(with_coords) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_map_spec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/generator/blocks/specs/map.py`:

```python
"""Map block spec — locations with coordinates."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import MapBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class MapBlockSpec(BlockSpec):
    kind: ClassVar = "map"
    data_schema: ClassVar = MapBlockData
    template_path: ClassVar = "blocks/map.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least one geocoded location.",
        min_sources=1,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `map` block.

Schema:
- locations: 1-6 Location. Each has:
    - name (place label)
    - lat / lon (decimal degrees; both required to render a pin)
    - note (<=80 chars, what happened here?)
    - source_id

Only include locations whose coordinates you can verify from evidence.
"""

    def is_minimum_viable(self, data: MapBlockData) -> bool:
        return any(
            loc.lat is not None and loc.lon is not None for loc in data.locations
        )
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/test_map_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/specs/map.py tests/blocks/specs/test_map_spec.py
git commit -m "feat(blocks): MapBlockSpec"
```

---

## Task 10: `ReactionsBlockSpec`

**Files:**
- Create: `src/generator/blocks/specs/reactions.py`
- Test: `tests/blocks/specs/test_reactions_spec.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_reactions_spec.py`:

```python
from generator.blocks.schema import QuoteCard, ReactionsBlock
from generator.blocks.specs.reactions import ReactionsBlockSpec


def _card(sentiment="neutral") -> QuoteCard:
    return QuoteCard(
        author="A",
        author_role="role",
        quote="q",
        sentiment=sentiment,  # type: ignore[arg-type]
        source_id="s1",
    )


def test_reactions_spec_metadata():
    spec = ReactionsBlockSpec()
    assert spec.kind == "reactions"
    assert spec.template_path == "blocks/reactions.html"


def test_reactions_minimum_viable_needs_two_cards_and_two_sentiments():
    spec = ReactionsBlockSpec()
    one = ReactionsBlock(cards=[_card("positive")])
    same = ReactionsBlock(cards=[_card("positive"), _card("positive")])
    diverse = ReactionsBlock(cards=[_card("positive"), _card("negative")])
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(same) is False
    assert spec.is_minimum_viable(diverse) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_reactions_spec.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/generator/blocks/specs/reactions.py`:

```python
"""Reactions block spec — up to 4 quote cards across multiple sentiments."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import ReactionsBlock
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class ReactionsBlockSpec(BlockSpec):
    kind: ClassVar = "reactions"
    data_schema: ClassVar = ReactionsBlock
    template_path: ClassVar = "blocks/reactions.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 2 quotes spanning >= 2 sentiments or stakeholder tiers.",
        min_sources=2,
        min_publishers=2,
        forbid_single_perspective=True,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `reactions` block.

Schema:
- cards: 2-4 QuoteCard. Each has:
    - author, author_role
    - quote (verbatim, <=240 chars; do NOT paraphrase)
    - sentiment: "positive" | "neutral" | "negative"
    - stakeholder_tier: "stakeholder" | "adjacent" | "third_party"
    - author_image_url (optional)
    - source_id (required)

The cards together must show >=2 distinct sentiments OR span stakeholder vs
third_party. A row of four cheerleaders is a fail.
"""

    def is_minimum_viable(self, data: ReactionsBlock) -> bool:
        if len(data.cards) < 2:
            return False
        sentiments = {c.sentiment for c in data.cards}
        return len(sentiments) >= 2
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/test_reactions_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/generator/blocks/specs/reactions.py tests/blocks/specs/test_reactions_spec.py
git commit -m "feat(blocks): ReactionsBlockSpec"
```

---

## Task 11: Wire up the registry

**Files:**
- Modify: `src/generator/blocks/specs/__init__.py`
- Test: `tests/blocks/specs/test_registry.py`

- [ ] **Step 1: Write the failing test**

Create `tests/blocks/specs/test_registry.py`:

```python
import pytest

from generator.blocks.specs import ALL_BLOCK_KINDS, BlockSpec, get_spec


def test_registry_covers_all_seven_block_kinds():
    expected = {
        "paragraph",
        "timeline",
        "chart",
        "newsfeed",
        "factsheet",
        "map",
        "reactions",
    }
    assert set(ALL_BLOCK_KINDS) == expected


@pytest.mark.parametrize(
    "kind",
    ["paragraph", "timeline", "chart", "newsfeed", "factsheet", "map", "reactions"],
)
def test_get_spec_returns_subclass(kind):
    spec_cls = get_spec(kind)
    assert issubclass(spec_cls, BlockSpec)
    assert spec_cls.kind == kind


def test_get_spec_unknown_kind_raises():
    with pytest.raises(KeyError):
        get_spec("not_a_kind")  # type: ignore[arg-type]


def test_each_spec_has_required_classvars():
    for kind in ALL_BLOCK_KINDS:
        spec_cls = get_spec(kind)
        # ClassVars must be defined on the concrete class (not just inherited
        # as abstract).
        assert spec_cls.data_schema is not None
        assert spec_cls.template_path.startswith("blocks/")
        assert spec_cls.extraction_prompt_fragment.strip()
        assert spec_cls.default_acceptance.description
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/blocks/specs/test_registry.py -v`
Expected: FAIL with `ImportError: cannot import name 'ALL_BLOCK_KINDS'`.

- [ ] **Step 3: Wire up registry imports**

Replace `src/generator/blocks/specs/__init__.py` with:

```python
"""BlockSpec registry. One spec per BlockKind, registered on import.

Importing this package eagerly imports each spec module so the
`_REGISTRY` is fully populated. Callers use `get_spec(kind)`.
"""

from __future__ import annotations

from generator.blocks.specs.base import BlockSpec
from generator.schema import BlockKind

_REGISTRY: dict[BlockKind, type[BlockSpec]] = {}

# Eagerly import each spec so __init_subclass__ registers it.
from generator.blocks.specs import paragraph as _paragraph  # noqa: E402, F401
from generator.blocks.specs import timeline as _timeline  # noqa: E402, F401
from generator.blocks.specs import chart as _chart  # noqa: E402, F401
from generator.blocks.specs import factsheet as _factsheet  # noqa: E402, F401
from generator.blocks.specs import newsfeed as _newsfeed  # noqa: E402, F401
from generator.blocks.specs import map as _map  # noqa: E402, F401
from generator.blocks.specs import reactions as _reactions  # noqa: E402, F401


def get_spec(kind: BlockKind) -> type[BlockSpec]:
    """Return the BlockSpec subclass for the given kind. Raises KeyError if unknown."""
    return _REGISTRY[kind]


ALL_BLOCK_KINDS: tuple[BlockKind, ...] = tuple(_REGISTRY.keys())

__all__ = ["BlockSpec", "get_spec", "ALL_BLOCK_KINDS"]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/blocks/specs/ -v`
Expected: PASS — registry test + all 7 per-spec tests, ~20 tests total.

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -q`
Expected: All tests pass; no regressions in existing pipeline tests (because nothing is wired in yet).

- [ ] **Step 6: Lint and format**

Run: `uv run ruff check src/generator/blocks/specs/ tests/blocks/specs/ tests/schema/`
Then: `uv run ruff format src/generator/blocks/specs/ tests/blocks/specs/ tests/schema/`

Expected: no issues.

- [ ] **Step 7: Commit**

```bash
git add src/generator/blocks/specs/__init__.py tests/blocks/specs/test_registry.py
git commit -m "feat(blocks): wire BlockSpec registry with get_spec()"
```

---

## Task 12: Sanity check — old pipeline still works end-to-end

This task does not write new code. It confirms Plan 1's purely-additive promise.

- [ ] **Step 1: Run the full integration test**

Run: `uv run pytest tests/integration/ -v`
Expected: PASS. (The `--auto` end-to-end test uses mocked LLM + HTTP via respx; should be untouched by additive schema changes.)

- [ ] **Step 2: Confirm `uv run generate run --auto` still imports cleanly**

Run: `uv run generate --help`
Expected: prints CLI help with subcommands `run` and `regen-module`, no import errors.

- [ ] **Step 3: Final commit (only if any incidental fixes were needed)**

If Steps 1-2 surfaced a problem, fix and commit; otherwise skip.

---

## What's NOT in Plan 1

- No changes to `Module` ABC, `NeedCurationPlan`, `extract.py`, `fetch.py`, `plan.py`, `converter.py`, or templates.
- No CLI changes.
- No `Module` deletions.
- No feature flag yet — that comes in Plan 2 when the new planner first runs.

## Spec coverage check

Re-reading the brainstorming decisions against this plan:

- ✅ 6 backbone sections — `BackboneSectionId` literal in Task 1.
- ✅ Bullets as paragraph variant — Task 2.
- ✅ `BlockSpec` declares data shape + prompt fragment + minimum-viable + default acceptance — Tasks 3-10.
- ✅ Registry — Task 11.
- ✅ Old pipeline untouched — Task 12 verification.
- ✅ Curation as one-shot LLM and research-loop budgets are NOT in this plan (Plans 2-3) — by design.

## Acceptance for "Plan 1 done"

- `uv run pytest -q` passes.
- `uv run ruff check .` passes.
- `git log --oneline` shows ~10-12 small commits, all on a feature branch.
- The old `uv run generate run --auto "..."` command runs successfully on a sample event (manual smoke test optional but recommended).
