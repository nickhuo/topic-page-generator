# Editor Architecture — Plan 5: Cleanup & Legacy Removal

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **DESTRUCTIVE PLAN.** Deletes ~3,700 LOC across 31 files and rewrites top-level docs. Order of operations matters: flip default first, then delete tests, then delete code, then delete schemas, then update docs. Each step must leave `uv run pytest -q` green.

**Goal:** Make the editor architecture the only architecture. Delete the legacy `Module`-driven pipeline, rename `regen-module` → `regen-section`, retitle HITL action kinds, and rewrite the architecture docs.

**Tech Stack:** Python 3.12, Pydantic v2, pytest, uv, ruff.

---

## Order of operations (locked)

1. **Flip default** — editor path runs always; remove `USE_EDITOR_ARCHITECTURE` env-flag check
2. **HITL terminology** — `editor/prompt_cli.py` + `EditorActionKind`/`EditorActionTarget` schema updates
3. **CLI `regen-module` → `regen-section`** — rewrite to use BlockSpec extraction
4. **Delete legacy tests** — `tests/modules/`, `tests/pipeline/test_{plan,fetch,extract,consistency,extract_e2e}.py`, `tests/integration/test_end_to_end.py`, `tests/integration/test_regen_module.py`
5. **Delete legacy code** — `src/generator/modules/`, `src/generator/pipeline/{plan,fetch,extract,consistency}.py`, `src/generator/blocks/converter.py`, `src/generator/prompts/{plan,aesthetic,consistency}.py`
6. **Delete legacy schemas** — `Module*` classes, `NeedCurationPlan`, `NeedPlanOutput`, `AestheticPlanOutput`, `FetchQuery`, `FetchAngle`, `TierQuota`, `Slot`, EventPage legacy fields, etc.
7. **Repair test/fixture fallout** — `tests/test_schema.py`, `tests/fixtures.py`, `tests/integration/test_render_two_column.py` — rewrite to use editorial path / RenderedSection
8. **Update CLAUDE.md** — rewrite architecture section
9. **Update docs/** — `PRD.md`, `DESIGN.md`, `schema.md`, `agents/domain.md`
10. **New minimal e2e smoke test** — replaces `test_end_to_end.py`
11. **Sanity check** — pytest, ruff, manual smoke

---

## Task 1: Flip default — remove env flag

**Files:**
- Modify: `src/generator/cli.py`

The editor path becomes default. All legacy stage invocations are removed in later tasks; for now keep them — Task 5 deletes them.

- [ ] **Step 1: Restructure cli.py `_run()` body**

The current `_run()` has two branches: the legacy 9-stage flow + an `if USE_EDITOR_ARCHITECTURE` early-return block that takes the editor path.

After Task 1, `_run()` should:
1. Run ground stage (shared)
2. Always run the editor path (no env-flag check)
3. Never run the legacy stages

Edit `src/generator/cli.py`:
- Remove the `if os.getenv("USE_EDITOR_ARCHITECTURE") == "1":` check
- Move the editor path code to run unconditionally after ground
- Delete the legacy stage code (Stage 2a Plan, Stage 3 Fetch, Stage 2b Aesthetic, Stage 4 Extract, Stage 5 Consistency, the module review loop, Stage 6 Render legacy, Stage 7 Deliver legacy + final_approval HITL)
- Keep the editor delivery's writing of `.html` and `.data.json`
- ADD: also write `<slug>.trace.json` (the editor path was skipping this; we want trace persistence)
- ADD: keep `prompter.final_approval(html_path)` call AFTER writing — even in auto mode this just records an `approve_page` action

Pseudocode for the cleaned-up `_run()`:

```python
async def _run() -> None:
    # Stage 1: Ground (with optional reformulation loop) — UNCHANGED.
    current_sentence = sentence
    while True:
        with recorder.stage("ground"):
            ground_out = await ground.run(current_sentence)
            ...
        decision, payload = prompter.ground_review(ground_out)
        if decision == "retry" and isinstance(payload, str):
            current_sentence = payload
            continue
        if decision == "reject" or not ground_out.is_hot_event:
            raise typer.Exit(code=5)
        ground_out = payload
        break

    if ground_out.facts is None or not ground_out.canonical_title:
        raise typer.Exit(code=4)

    # Editor architecture: planners → research → block_extract → render → deliver
    backbone = build_backbone_sections(ground_out.facts, ...)
    with recorder.stage("curation"):
        curation_out = await run_curation_stage(...)
    combined = SectionPlanOutput(sections=backbone + list(curation_out.sections))

    # (optional plan review HITL — defer; not in scope for Task 1)

    wd_source, _ = await fetch_wikidata(...)
    wp_card = await fetch_wikipedia_card(...)
    seed_sources = [wd_source] if wd_source else []

    with recorder.stage("research"):
        pools = await run_research_stage(...)

    with recorder.stage("block_extract"):
        rendered_sections = await run_block_extract_stage(...)

    subject_e = subject_from_facts(ground_out.facts, ground_out.canonical_title)
    all_sources = list({s.id: s for pool in pools.values() for s in pool}.values())
    with recorder.stage("render"):
        page = build_editorial_page(
            input_sentence=sentence, page_id=page_id, subject=subject_e,
            layout=EventLayout(preset_id="product_focus", overrides=None),
            sources=all_sources + seed_sources,
            editorial_sections=rendered_sections,
            trace_id=recorder.trace_id,
            meta=EventMeta(
                last_updated=_now(),
                editor_approved=True,
                editor_id="cli_user@local",
                pipeline_trace_id=recorder.trace_id,
            ),
            wikipedia_card=wp_card,
        )
        html = render_html(page)

    # Stage 7: Deliver — write all three artifacts + final approval.
    slug = slugify(ground_out.canonical_title)
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    html_path = _OUTPUT_DIR / f"{slug}.html"
    data_path = _OUTPUT_DIR / f"{slug}.data.json"
    trace_path = _OUTPUT_DIR / f"{slug}.trace.json"
    html_path.write_text(html, encoding="utf-8")
    data_path.write_text(page.model_dump_json(indent=2), encoding="utf-8")

    final_decision = prompter.final_approval(html_path)
    # In auto mode this returns "approve" and records the action.
    trace = recorder.finalize(
        auto_mode=auto,
        final_outcome=final_decision if isinstance(final_decision, str) else "approve",
    )
    trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
    console.print(f"[green]✓[/green] Wrote {slug}.html / .data.json / .trace.json")
```

Note: `_now()` is the existing helper from `editor.prompt_cli`. Keep all `recorder.stage(...)` wrappers — the trace structure stays the same shape, just with different stage names.

- [ ] **Step 2: Remove `os` import if no longer used** (it's still used elsewhere — leave it).

- [ ] **Step 3: Confirm imports**

After Task 1, cli.py should NO LONGER import:
- `from generator.pipeline import consistency, extract, ground, plan, render` — change to: `from generator.pipeline import ground, render`
- `from generator.pipeline.extract import extract_one_module` — REMOVE
- `from generator.pipeline.fetch import EmptyEvidencePoolError, run_fetch_stage` — REMOVE
- `from generator.modules.base import PlanContext` — REMOVE
- `httpx` — REMOVE (was used for fetch error type)

These imports are dead. Removing them now is fine because the code paths that used them are gone.

But: `regen-module` subcommand (lines 410+) still uses many of these. Move regen-module imports inside the function for now; Task 3 rewrites it.

- [ ] **Step 4: Run tests**

`uv run pytest -q` — expect:
- Legacy unit tests for fetch/extract/plan/consistency still pass (they test the modules directly, not the CLI).
- `tests/integration/test_end_to_end.py` may BREAK (it runs the legacy CLI path which is now gone). Mark with `pytest.skip` for this commit; deletion in Task 4.
- `tests/integration/test_regen_module.py` should still pass (uses regen-module subcommand directly).
- All editor-path tests still green.

If `test_end_to_end.py` fails: at the top of the test module add `pytest.skip("legacy path removed", allow_module_level=True)`. We delete it in Task 4.

- [ ] **Step 5: Lint + commit**

```bash
uv run ruff check src/generator/cli.py
git add src/generator/cli.py tests/integration/test_end_to_end.py
git commit -m "feat(cli): editor architecture is now the default — legacy stages removed from CLI"
```

---

## Task 2: HITL terminology

**Files:**
- Modify: `src/generator/schema.py` — rename action kinds + target fields
- Modify: `src/generator/editor/prompt_cli.py` — module_review → section_review (or remove)
- Modify: relevant tests

The editor-architecture path currently doesn't invoke `prompter.module_review()` (we removed that loop in Task 1). The remaining HITL touchpoints are `ground_review` and `final_approval`. So `module_review` becomes orphan code.

**Decision:** Delete `module_review` entirely. Add a new `section_review` method later when we wire HITL into the editor path (out of scope for Plan 5 — file as follow-up). Rename action kinds in the enum to use section vocabulary; the only remaining caller of `regenerate_module` (in `final_approval` for the "regen <kind>" path) gets removed too.

- [ ] **Step 1: Update `EditorActionKind` enum**

In `src/generator/schema.py`, replace the `EditorActionKind` Literal with:

```python
EditorActionKind = Literal[
    "accept_section",
    "regenerate_section",
    "edit_section_field",
    "skip_section",
    "override_archetype",
    "override_preset",
    "approve_page",
    "reject_page",
    "save_draft",
]
```

- [ ] **Step 2: Rename `EditorActionTarget.module_kind` → `section_id`**

In `src/generator/schema.py`:

```python
class EditorActionTarget(_Frozen):
    section_id: str | None = None
    field_path: str | None = None
```

- [ ] **Step 3: Update `editor/prompt_cli.py`**

In `src/generator/editor/prompt_cli.py`:
- Delete the `module_review` method entirely (lines ~233–311).
- In `ground_review` and `plan_review` and `final_approval`: change `accept_module` → `accept_section`, `edit_module_field` → `edit_section_field`, `regenerate_module` → `regenerate_section`, `skip_module` → `skip_section` wherever they appear.
- `final_approval`'s "regen <kind>" branch returns `("regen", kind)` — that branch is no longer plumbed by the CLI (Task 1 dropped the regen loop). Keep the branch — it still records `regenerate_section` for users who type it; the caller now just ignores the `("regen", _)` tuple. Or remove that menu option entirely; simpler.

For simplicity, **remove** the "[r <kind>] regenerate" menu option in `final_approval` so the menu becomes just `[y] approve / [n] reject`. The return type becomes `Literal["approve", "reject"]` (no tuple).

Delete `plan_review` too — there is no need_plan to review in the editor architecture. The `--review-plan` CLI flag becomes a no-op; remove it from the typer Option in Task 1 (and consider whether to add a `--review-sections` flag later).

Actually: leave `plan_review` and `--review-plan` as a follow-up. Mark `plan_review` with a deprecation comment and have it return its input unchanged. We can clean it in a separate PR.

- [ ] **Step 4: Update test_schema.py and any HITL tests**

Run `grep -r "module_kind\|accept_module\|regenerate_module\|edit_module_field\|skip_module" src/ tests/` and update each hit:
- Replace `module_kind=` with `section_id=` in EditorActionTarget construction
- Replace action-kind strings with their `_section` equivalents

If a test was specifically testing `module_review`, it can be deleted (alongside the method).

- [ ] **Step 5: Run tests**

`uv run pytest -q` — fix any remaining breakages.

- [ ] **Step 6: Lint + commit**

```bash
git add src/generator/schema.py src/generator/editor/prompt_cli.py tests/
git commit -m "feat(editor): rename HITL action kinds to section vocabulary; drop module_review"
```

---

## Task 3: Rewrite `regen-module` → `regen-section`

**Files:**
- Modify: `src/generator/cli.py` — replace the `regen-module` Typer command with `regen-section`
- Modify: `tests/integration/test_regen_module.py` → rename to `test_regen_section.py` and rewrite

`regen-section` reconstructs a single `SectionPlan` from the saved `EventPage` and re-runs `extract_one_section()` with that section's evidence pool.

- [ ] **Step 1: Read the current regen-module body** in `cli.py` to confirm structure of EventPage loading + trace update.

- [ ] **Step 2: Write the new subcommand**

In `src/generator/cli.py`:

```python
@app.command("regen-section")
def regen_section(
    section_id: str = typer.Argument(..., help="Section id to regenerate (e.g. 'overview')."),
    data_json_path: Path = typer.Argument(
        ..., exists=True, readable=True, dir_okay=False,
        help="Path to an existing <slug>.data.json file.",
    ),
) -> None:
    """Re-run block extraction for one section against the saved evidence pool."""
    load_dotenv(".env")
    load_dotenv(".env.local", override=True)
    _reset_llm_calls()

    raw = json.loads(data_json_path.read_text(encoding="utf-8"))
    try:
        page = EventPage.model_validate(raw)
    except ValidationError as exc:
        console.print(f"[bold red]Invalid EventPage:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    if page.editorial_sections is None:
        console.print("[bold red]data.json has no editorial_sections.[/bold red]")
        raise typer.Exit(code=2)

    existing = next(
        (s for s in page.editorial_sections if s.section_id == section_id), None
    )
    if existing is None:
        console.print(f"[bold red]Unknown section_id: {section_id}[/bold red]")
        raise typer.Exit(code=1)

    # Reconstruct a SectionPlan stub — we don't have the planner's intent/acceptance
    # on disk, so use defaults from the BlockSpec.
    from generator.blocks.specs import get_spec
    spec_cls = get_spec(existing.block_kind)
    stub_section = SectionPlan(
        section_id=existing.section_id,
        kind="curated" if existing.section_id not in {
            "overview", "key_takeaways", "timeline",
            "background", "key_facts", "media_coverage",
        } else "backbone",
        title=existing.section_id.replace("_", " ").title(),
        rank=1,
        block_kind=existing.block_kind,
        intent="regen",
        acceptance=spec_cls.default_acceptance,
    )

    # Use the saved sources_used as the evidence pool. This is narrower than
    # the original per-section pool, but reflects what we know is on disk.
    evidence = existing.sources_used or page.sources

    async def _do() -> RenderedSection | None:
        return await extract_one_section(
            section=stub_section,
            sources=evidence,
            canonical_title=page.meta.canonical_title if hasattr(page.meta, "canonical_title") else "",
        )

    new_section = asyncio.run(_do())
    if new_section is None:
        console.print("[bold red]Regen produced no usable section.[/bold red]")
        raise typer.Exit(code=4)

    # Replace in place.
    updated_sections = [
        new_section if s.section_id == section_id else s
        for s in page.editorial_sections
    ]
    updated_page = page.model_copy(update={"editorial_sections": updated_sections})

    data_json_path.write_text(
        updated_page.model_dump_json(indent=2), encoding="utf-8"
    )
    html_path = data_json_path.with_suffix(".html").with_name(
        data_json_path.stem.replace(".data", "") + ".html"
    )
    # If file naming doesn't match assumptions, just rebuild path:
    slug = data_json_path.stem
    if slug.endswith(".data"):
        slug = slug[:-len(".data")]
    html_path = data_json_path.parent / f"{slug}.html"
    html_path.write_text(render_html(updated_page), encoding="utf-8")

    # Append trace action.
    trace_path = data_json_path.parent / f"{slug}.trace.json"
    if trace_path.exists():
        trace_raw = json.loads(trace_path.read_text(encoding="utf-8"))
        action = {
            "action_at": datetime.now(timezone.utc).isoformat(),
            "actor": "cli_user@local",
            "action": "regenerate_section",
            "target": {"section_id": section_id, "field_path": None},
            "before": None,
            "after": None,
            "reason": "regen-section CLI",
        }
        trace_raw.setdefault("editor_actions", []).append(action)
        trace_path.write_text(json.dumps(trace_raw, indent=2), encoding="utf-8")

    console.print(f"[green]✓[/green] Regenerated section {section_id}")
```

DELETE the old `regen-module` command entirely.

Imports needed at top of cli.py: `from datetime import datetime, timezone`, `from generator.pipeline.block_extract import extract_one_section`, `from generator.schema import EventPage, SectionPlan, RenderedSection`. Add as needed.

- [ ] **Step 3: Rename + rewrite integration test**

```bash
git mv tests/integration/test_regen_module.py tests/integration/test_regen_section.py
```

Rewrite the test contents to:
- Use a fixture EventPage with `editorial_sections` populated (build one inline, ~6 lines)
- Mock `extract_one_section` to return a new RenderedSection
- Assert: exit 0, data.json updated, html written, trace.json action appended

Keep the test count low (3-4 tests). Reuse the legacy test's structure where possible.

- [ ] **Step 4: Run tests**

`uv run pytest tests/integration/test_regen_section.py -v`

- [ ] **Step 5: Lint + commit**

```bash
git add src/generator/cli.py tests/integration/test_regen_section.py
git rm tests/integration/test_regen_module.py   # if not already moved by git mv
git commit -m "feat(cli): replace regen-module with regen-section"
```

---

## Task 4: Delete legacy tests

These tests target code we delete in Task 5. Deleting them first prevents red builds mid-Task-5.

**Files to delete:**
- `tests/modules/` — entire directory (12 files)
- `tests/pipeline/test_plan.py`
- `tests/pipeline/test_fetch.py`
- `tests/pipeline/test_extract.py`
- `tests/pipeline/test_extract_e2e.py`
- `tests/pipeline/test_consistency.py`
- `tests/integration/test_end_to_end.py`

- [ ] **Step 1:** Delete the files.

```bash
git rm -r tests/modules/
git rm tests/pipeline/test_plan.py tests/pipeline/test_fetch.py tests/pipeline/test_extract.py tests/pipeline/test_extract_e2e.py tests/pipeline/test_consistency.py
git rm tests/integration/test_end_to_end.py
```

- [ ] **Step 2:** `uv run pytest -q` — expect green; ~25 legacy tests gone, ~270 remain.

- [ ] **Step 3:** Commit:

```bash
git commit -m "test: delete legacy module + pipeline tests"
```

---

## Task 5: Delete legacy code

Order matters: delete *.py files that nothing imports anymore. After Task 4 removed their tests, the only consumers were each other and `cli.py` (Task 1 stripped those imports).

- [ ] **Step 1:** Confirm nothing imports the doomed modules:

```bash
grep -rn "from generator.modules\|from generator.pipeline.plan\|from generator.pipeline.fetch\|from generator.pipeline.extract\|from generator.pipeline.consistency\|from generator.blocks.converter\|from generator.prompts.plan\|from generator.prompts.aesthetic\|from generator.prompts.consistency" src/ tests/
```

If anything still imports these and isn't `cli.py:regen-module` (already deleted by Task 3), STOP and fix that consumer first.

- [ ] **Step 2:** Delete the files:

```bash
git rm -r src/generator/modules/
git rm src/generator/pipeline/plan.py
git rm src/generator/pipeline/fetch.py
git rm src/generator/pipeline/extract.py
git rm src/generator/pipeline/consistency.py
git rm src/generator/blocks/converter.py
git rm src/generator/prompts/plan.py
git rm src/generator/prompts/aesthetic.py
git rm src/generator/prompts/consistency.py
```

- [ ] **Step 3:** Update `src/generator/blocks/__init__.py` — remove the `module_to_block` re-export. Leave only what's still useful (or empty it out).

- [ ] **Step 4:** Update `src/generator/pipeline/__init__.py` — if it has explicit re-exports of `plan`, `fetch`, `extract`, `consistency`, remove them. The module `render` and `ground` remain.

- [ ] **Step 5:** `uv run pytest -q` — green. Confirm no import errors.

- [ ] **Step 6:** Commit:

```bash
git commit -m "feat: delete legacy module-driven pipeline code"
```

---

## Task 6: Delete legacy schemas + repair fallout

**Files:**
- Modify: `src/generator/schema.py` — delete legacy classes
- Modify: `tests/fixtures.py` — rewrite `canned_event_page()` to use editorial_sections
- Modify: `tests/test_schema.py` — drop tests of deleted types
- Modify: `tests/integration/test_render_two_column.py` — adapt to new fixture shape

### What to delete in schema.py

- All TypedModule variants: `HeroModule`, `InfoboxModule`, `ScheduleModule`, `KPINumbersModule`, `ComparisonModule`, `ChangelogModule`, `ReactionsModule`, `MediaCoverageModule`, `OfficialStatementsModule`, `WhereToWatchModule`, `BackgroundModule`
- Their data classes: `HeroData`, `OverviewBullet`, `InfoboxRow`, `InfoboxData`, `ScheduleItem`, `ScheduleData`, `KPITile`, `KPINumbersData`, `ComparisonSubject`, `ComparisonCell`, `ComparisonAxis`, `ComparisonData`, `ChangelogEntry`, `ChangelogData`, `ReactionItem`, `ReactionAggregate`, `ReactionsData`, `MediaCoverageItem`, `MediaCoverageData`, `OfficialStatementItem`, `OfficialStatementsData`, `WhereToWatchChannel`, `WhereToWatchData`, `BackgroundParagraph`, `BackgroundData`
- `_BaseModule`, `TypedModule` union
- `NeedCurationPlan`, `NeedPlanOutput`, `AestheticPlanOutput`, `AestheticOverrides`, `AestheticPresetId`, `AestheticPreset`
- `FetchQuery`, `FetchAngle`, `TierQuota`
- `Slot` literal (already documented as legacy)
- `NeedId` Literal, `_NEEDS_ORDER` — KEEP if `Source.serves_needs` still references `list[NeedId]`. Check; if so, change `Source.serves_needs: list[str]` (the field becomes orphan but harmless; or delete it entirely)

### What to keep

- `Source`, `Publisher`, `SourceRights`, `Citation`
- `EventFacts`, `GroundOutput`
- `RenderedSection`, `SectionPlan`, `SectionPlanOutput`, `AcceptanceCriteria`, `BackboneSectionId`, `SectionKind`, `BlockKind`
- `ResearchEvalResult`
- `Trace`, `StageTrace`, `LLMCall`, `EditorAction`, `EditorActionKind`, `EditorActionTarget`, `TraceApproval`
- `EventPage`, `EventSubject`, `EventLayout`, `EventMeta`, `WikipediaCardData`
- `ConfidenceFlag`, `ConfidenceSignals`, `ModuleConfidence`

### EventPage cleanup

Remove these fields:
- `modules: list[TypedModule]`
- `needs_coverage: dict[NeedId, list[ModuleId]]`
- `uncovered_needs: list[NeedId]`
- `need_plans: list[NeedCurationPlan]`

Make `editorial_sections: list[RenderedSection]` required (no longer Optional).

- [ ] **Step 1:** Delete the classes from schema.py. Run `uv run python -c "from generator.schema import EventPage; print('ok')"` after each chunk to surface errors early.

- [ ] **Step 2:** Update `tests/fixtures.py`:
   - `canned_event_page()` currently builds an EventPage with TypedModules. Rewrite to build one with `editorial_sections=[...]` containing 2-3 RenderedSections with simple ParagraphBlockData / NewsfeedBlockData. Remove all module imports.

- [ ] **Step 3:** Update `tests/test_schema.py`:
   - Delete any test that constructs a TypedModule variant or `NeedCurationPlan`.
   - Keep tests of Source, EventFacts, etc.

- [ ] **Step 4:** Update `tests/integration/test_render_two_column.py`:
   - These tests use `canned_event_page()`. With the fixture rewritten in Step 2, they should still produce HTML — but some assertions may target legacy markup. Audit and rewrite each broken assertion.
   - Hero rendering test (`test_hero_renders_updated_time`) — `EventPage.modules` is gone; if hero comes from chrome, drop the test or rewrite it to point at editorial_sections[0].
   - Reactions tests — drop unless `editorial_sections` contains a reactions section.

   This is fiddly. Don't try to keep every assertion green by adding shims — when a test asserts about legacy markup that doesn't exist anymore, **delete the test**. Coverage of editor-path rendering lives in `test_render_editorial.py` already.

- [ ] **Step 5:** `uv run pytest -q` — green.

- [ ] **Step 6:** `uv run ruff check .` — green.

- [ ] **Step 7:** Commit:

```bash
git add src/generator/schema.py tests/
git commit -m "feat(schema): delete legacy Module/NeedPlan/FetchQuery schemas and adapt fixtures"
```

---

## Task 7: Update CLAUDE.md

Rewrite the architecture-related sections to describe the editor architecture as the only architecture. Preserve toolchain notes, agent workflow notes, and the schema-discipline emphasis.

**File:** `/Users/nickhuo/GitHub/topic-page-generator/CLAUDE.md`

- [ ] **Step 1:** Rewrite. Use this structure:

```markdown
# CLAUDE.md

## Toolchain
(unchanged — uv, ruff, etc.)

## Commands

uv sync
uv run generate run "<one-sentence event>"            # full editor pipeline, interactive HITL
uv run generate run --auto "<sentence>"               # bypass HITL
uv run generate regen-section <section_id> output/<slug>.data.json   # re-extract one section

uv run pytest, uv run ruff check ., uv run ruff format .

Required env vars: OPENROUTER_API_KEY, TAVILY_API_KEY. Optional MODEL_GROUND, MODEL_CURATION, MODEL_RESEARCH_QUERY, MODEL_RESEARCH_EVAL, MODEL_BLOCK_EXTRACT.

CLI exit codes: 1 LLM config, 2 schema validation, 3 network/fetch, 4 LLM bad output, 5 not a hot event / user rejected.

## Architecture (editor architecture)

CLI runs an async editorial pipeline orchestrated in `src/generator/cli.py::generate`. Each stage is wrapped by `TraceRecorder.stage(...)`.

Stages and where they live (all under `src/generator/pipeline/` unless noted):

1. **ground** — gate + fact extraction (`ground.py` + `prompts/ground.py`)
2. **curation** — backbone (deterministic, 6 sections via `backbone_planner.py`) + LLM curation (0–4 extra sections via `curation_planner.py` + `prompts/curation.py`)
3. **research** — per-section research loop (`research.py`, `research_eval.py`, `prompts/research_query.py`, `prompts/research_eval.py`). Budgets: max 3 iterations per section, max 4 Tavily calls per section, MAX_TOTAL_TAVILY=30 globally. Wikidata + Wikipedia card fetched once, prepended to every section's pool.
4. **block_extract** — `block_extract.py` extracts one `RenderedSection` per `SectionPlan` using the matching `BlockSpec`. Citation integrity + `is_minimum_viable` gating per section.
5. **render** — `render.build_editorial_page()` + `render.render_html()`. Two-column layout (main + reference sidebar), horizontal sticky chip nav.
6. **deliver** — writes `output/<slug>.{html,data.json,trace.json}`; runs `final_approval` HITL.

**HITL** — `EditorPrompter` in `src/generator/editor/prompt_cli.py`. Touchpoints: `ground_review` (sentence reformulation / fact edit) and `final_approval` (approve/reject final HTML). Per-section review is planned but not yet wired.

**Schema discipline** — `src/generator/schema.py` is the single source of truth for `EventPage`, `RenderedSection`, `SectionPlan`, `Source`, `Trace`, `EditorAction`, `ResearchEvalResult`, etc. Every LLM call boundary validates with Pydantic; malformed output raises and is retried by tenacity. Citations are required on factual claims; unsourced assertions fail validation.

**LLM client** — `src/generator/llm/client.py` wraps OpenRouter via the openai SDK with tenacity retries. Stage models: `MODEL_<STAGE>` env var, fallbacks in `_STAGE_FALLBACK_MODELS`.

**Prompts** — `src/generator/prompts/`: one file per LLM-issuing stage. `base_preamble.py` is shared.

**Block layer** — `src/generator/blocks/`:
- `schema.py` — `RenderBlock` discriminated union (7 kinds: paragraph, timeline, chart, newsfeed, factsheet, map, reactions) and their data classes.
- `specs/` — `BlockSpec` per kind. Each owns `data_schema`, `extraction_prompt_fragment`, `template_path`, `default_acceptance`, `is_minimum_viable()`. Registry via `get_spec(kind)`.

**`regen-section` subcommand** reconstructs a single `SectionPlan` stub from a saved `EventPage.editorial_sections[i]` and re-runs `block_extract.extract_one_section()` against that section's saved `sources_used`.

## Tests

`tests/` mirrors `src/generator/`. Pipeline unit tests under `tests/pipeline/`, prompt builders under `tests/prompts/`, blocks under `tests/blocks/specs/`, schema under `tests/schema/`, end-to-end + render integration under `tests/integration/`.

## Domain docs

Single-context: `CONTEXT.md` + ADRs under `docs/adr/`.

## Agent workflow
(unchanged — Linear, triage labels, etc.)
```

Adapt to actual existing wording where reasonable. Keep `userEmail`, `currentDate` blocks unchanged.

- [ ] **Step 2:** Commit:

```bash
git add CLAUDE.md
git commit -m "docs(claude): rewrite architecture section for editor pipeline"
```

---

## Task 8: Update docs/{PRD,DESIGN,schema}.md

These docs describe the legacy architecture in detail. Plan 5's scope says rewrite them but doesn't enumerate every section. **Pragmatic approach:** add a "Status: superseded" header to the legacy architecture sections, then append a new short "Editor architecture (current)" section that cross-references CLAUDE.md and the plan files. This is honest about the migration without a full rewrite.

**Files:**
- Modify: `docs/PRD.md`
- Modify: `docs/DESIGN.md`
- Modify: `docs/schema.md`
- Modify: `docs/agents/domain.md` (light)

- [ ] **Step 1:** For each of PRD.md, DESIGN.md, schema.md — read the file, find the architecture / pipeline / module sections, and replace them with a pointer to CLAUDE.md + the editor-architecture plans. Specifically:

For each file, prepend:

```markdown
> **Status (2026-05-15):** This document predates the editor-architecture refactor.
> The current pipeline is documented in `CLAUDE.md` and detailed in
> `docs/superpowers/plans/2026-05-15-editor-architecture-*.md`. Sections below
> referring to the Module-driven pipeline, NeedPlanOutput, or extract.run are
> historical context only.
```

Then in each section that describes the legacy pipeline by stage, leave the content but add a footnote-style admonition. Do NOT delete content — it's historical record. Editing PRD/DESIGN to full parity is a follow-up.

- [ ] **Step 2:** `docs/agents/domain.md`: quick read; if it mentions module kinds or NeedIds, add a similar status banner.

- [ ] **Step 3:** Commit:

```bash
git add docs/
git commit -m "docs: mark PRD/DESIGN/schema as pre-editor-architecture; defer full rewrite"
```

---

## Task 9: Minimal e2e smoke test for the editor path

Replace the placeholder skipped `tests/integration/test_editor_architecture_flag.py` with a real test. Keep it minimal: mock all LLM endpoints, mock Tavily + Wikidata + Wikipedia, run the CLI, assert exit code 0 and output files exist.

- [ ] **Step 1:** Rename file (optional): `git mv tests/integration/test_editor_architecture_flag.py tests/integration/test_editor_e2e.py` — the env-flag concept is gone.

- [ ] **Step 2:** Implement using the same `respx.mock` + `monkeypatch` pattern as the deleted `test_end_to_end.py`. Mock these endpoints (in order called):
  - OpenRouter (catch-all for any chat/completions URL) — return a sequence of canned responses for ground, curation, research_query, research_eval (multiple), block_extract (multiple). Easiest pattern: use respx to register a single endpoint that cycles through a list of responses.
  - `generator.sources.tavily.fetch_tavily` — monkeypatch to return a small `list[Source]`.
  - `generator.sources.wikidata.fetch_wikidata` — monkeypatch to return `(None, {})`.
  - `generator.sources.wikipedia.fetch_wikipedia_card` — monkeypatch to return `None`.

  Plus envs: `monkeypatch.setenv("OPENROUTER_API_KEY", "sk-test")`, `monkeypatch.setenv("TAVILY_API_KEY", "tav-test")`.

- [ ] **Step 3:** Invoke CLI via `CliRunner` (`typer.testing.CliRunner()`) with `["run", "--auto", "test event sentence"]`. Assert exit code 0.

- [ ] **Step 4:** Assert `output/<slug>.html`, `output/<slug>.data.json`, `output/<slug>.trace.json` exist (use tmp_path + monkeypatch.chdir or `_OUTPUT_DIR` monkeypatch).

- [ ] **Step 5:** If the test gets too complex (mocking 5+ LLM endpoints in sequence), narrow the scope: mock everything to return the simplest valid responses (curation returns empty curated list → only backbone sections; research_eval always returns satisfied=True on first call → no iteration; block_extract returns minimum-viable paragraphs for each backbone section). The point is to prove the pipeline runs end-to-end; not to assert HTML quality.

- [ ] **Step 6:** Commit:

```bash
git add tests/integration/test_editor_e2e.py
git rm tests/integration/test_editor_architecture_flag.py  # if not already renamed
git commit -m "test(integration): minimal editor-pipeline smoke test"
```

---

## Task 10: Sanity check

- [ ] **Step 1:** `uv run pytest -q` — all tests pass.
- [ ] **Step 2:** `uv run ruff check .` — clean.
- [ ] **Step 3:** `uv run generate --help` — shows `run` and `regen-section` (no `regen-module`).
- [ ] **Step 4:** `git grep -in "^from generator.modules\|^from generator.pipeline.plan\|^from generator.pipeline.fetch\|^from generator.pipeline.extract\|^from generator.pipeline.consistency\|^from generator.blocks.converter\|^from generator.prompts.plan\|^from generator.prompts.aesthetic" src/ tests/` — empty result.
- [ ] **Step 5:** `git grep -i "NeedPlanOutput\|TypedModule\|FetchQuery\|module_to_block" src/ tests/` — empty (no live references).
- [ ] **Step 6:** Commit any incidental fixes from the sanity check.

---

## Acceptance for "Plan 5 done"

- `uv run pytest -q` passes.
- `uv run ruff check .` clean.
- `git grep` confirms no live references to deleted symbols.
- `output/` artifacts produced by the editor path on a real event are valid HTML and data.json (manual spot check — optional in CI).
- CLAUDE.md describes the editor architecture as the only architecture.
- ~3,700 LOC + ~31 files removed.

## What's NOT in Plan 5 (deferred follow-ups)

- Full rewrite of `docs/PRD.md`, `docs/DESIGN.md`, `docs/schema.md` (Plan 5 adds status banners; full rewrite is its own PR).
- `section_review` HITL touchpoint in the editor path (only `ground_review` and `final_approval` are wired; per-section interactive review is a follow-up).
- `--review-plan` CLI flag rework (kept as no-op deprecation for now).
- Trace migration helpers for old trace.json files (Plan 5 notes: old traces won't replay; no auto-converter).
- Parity-quality validation on a curated event corpus (a quality check by the human, not a code change).
