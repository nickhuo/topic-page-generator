# Editor Architecture — Plan 2: Backbone + Curation Planners (STUB)

> Detailed steps will be written after Plan 1 lands. This stub captures scope and inputs only.

**Goal:** Replace `run_plan_stage` with a two-phase editorial planner that emits `SectionPlanOutput` (introduced in Plan 1). Gate behind `USE_EDITOR_ARCHITECTURE=1` env var so old path keeps running by default.

**Inputs from Plan 1:** `SectionPlan`, `SectionPlanOutput`, `AcceptanceCriteria`, `BackboneSectionId`, `BlockSpec` registry.

## In scope

1. `src/generator/pipeline/backbone_planner.py` — deterministic, 0 LLM calls. Emits 6 backbone `SectionPlan`s:
   - `overview` → paragraph (prose), rank 1
   - `key_takeaways` → paragraph (bullets), rank 2
   - `timeline` → timeline, rank 3
   - `key_facts` → factsheet, rank 4
   - `background` → paragraph (prose), rank 5
   - `media_coverage` → newsfeed, rank 6
   Each pre-fills `title`, `intent`, and pulls `default_acceptance` from the spec.

2. `src/generator/pipeline/curation_planner.py` — one LLM call. Input: triage + disamb + backbone list. Output: 0-4 `SectionPlan`s with `kind="curated"`, free-form `section_id`, `block_kind` from closed enum.

3. `src/generator/prompts/curation.py` — prompt for the curation planner (lists triage type/tone, enumerates available block kinds, asks for additional sections that enrich reader experience).

4. New CLI flag plumbing in `src/generator/cli.py` — when `USE_EDITOR_ARCHITECTURE=1` env is set, call the new planners and stop (no fetch/extract yet — Plan 3+). Print the section plan JSON for inspection. This is the smoke-test path.

## Tests

- Unit: backbone planner emits all 6 sections with correct block kinds and `default_acceptance` populated.
- Unit: curation planner with mocked LLM returns valid `SectionPlan`s; rejects unknown `block_kind` via Pydantic.
- Integration: env-gated CLI path emits a section plan and exits cleanly without touching fetch/extract.

## Out of scope

- Research loop, extract, render — all later plans.
- Removing the old `run_plan_stage` — Plan 5.
