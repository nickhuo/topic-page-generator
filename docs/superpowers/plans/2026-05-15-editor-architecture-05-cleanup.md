# Editor Architecture — Plan 5: Cleanup & Legacy Removal (STUB)

> Detailed steps will be written after Plan 4 lands and the new path produces parity-quality output on real events.

**Goal:** Flip `USE_EDITOR_ARCHITECTURE=1` to the default and delete the legacy code paths.

## In scope

1. **Default-on the new path.** Remove the env-var gate; old planners/fetch/extract are no longer reachable.

2. **Delete legacy module code:**
   - `src/generator/modules/` directory (Module ABC + 11 module files)
   - `src/generator/blocks/converter.py` (replaced by direct BlockSpec extraction)
   - `src/generator/pipeline/plan.py` (replaced by backbone + curation planners)
   - `src/generator/pipeline/fetch.py` (replaced by `research.py`)
   - `src/generator/pipeline/extract.py` (replaced by `block_extract.py`)
   - All Module-specific Pydantic schemas in `schema.py`: `HeroModule`, `InfoboxModule`, `ScheduleModule`, `KPINumbersModule`, `ComparisonModule`, `ChangelogModule`, `ReactionsModule`, `MediaCoverageModule`, `OfficialStatementsModule`, `WhereToWatchModule`, `BackgroundModule`, `_BaseModule`, `TypedModule`.
   - Legacy `NeedCurationPlan` / `NeedPlanOutput` / `FetchAngle` / `FetchQuery` / `TierQuota` from `schema.py` (or keep `FetchQuery` if `research_query.py` reuses it).
   - `Slot` literal (already documented as legacy in CLAUDE.md).

3. **CLI rename:** `regen-module <kind>` → `regen-section <section_id>`. Stub regen flow to reconstruct a single `SectionPlan` from saved `EventPage` and re-run Plan 4's extractor.

4. **Trace/HITL updates:** `EditorActionTarget.module_kind` → `section_id`; `EditorActionKind` enum values `accept_module` / `regenerate_module` / `edit_module_field` / `skip_module` → `accept_section` / `regenerate_section` / `edit_section_field` / `skip_section`. Update `editor/prompt_cli.py` accordingly.

5. **Docs:** Update `CLAUDE.md`, `docs/schema.md`, `docs/PRD.md`, `docs/DESIGN.md` to describe the editor architecture as the only architecture. Delete Phase-1 / Phase-2 migration language.

6. **Trace migration:** Old trace.json files won't replay through the new pipeline. Document this in `CHANGELOG` if one exists; otherwise note in commit message.

## Tests

- Full test suite passes after deletions.
- Integration test for end-to-end `--auto` run on a fixture event.
- `regen-section` CLI test using a saved `EventPage` fixture.

## Acceptance

- `git grep -i "module\b"` returns zero results in `src/generator/` (other than the Python word in docstrings).
- `uv run generate run --auto "<event>"` produces a valid HTML page, equivalent or better quality than pre-refactor on a hand-picked spot-check set of 3-5 events.
