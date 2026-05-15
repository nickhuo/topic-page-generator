# Editor-Architecture Refactor — Roadmap

> Five-plan split. Each plan ships independently testable software; old pipeline keeps running until Plan 5 retires it.

**Vision:** Replace the linear `Plan → Fetch → Extract` pipeline with an editorial loop:

1. **Backbone planner** (deterministic) emits 6 always-on sections.
2. **Curation planner** (one-shot LLM) proposes event-typed extra sections.
3. **Per-section research loop** (agent, capped) iterates `query → fetch → eval → refine` until acceptance criteria are met.
4. **Block-driven extraction** fills each section's `BlockData` directly — no `Module` indirection.
5. **Page eval** stays as a final consistency pass.

The `Module` class disappears. `BlockSpec` (one per `BlockKind`) owns extraction prompt + render template + minimum-viable check.

---

## Plan split

| # | Plan | Status | File |
|---|---|---|---|
| 1 | **Foundation** — `BlockSpec` registry, section schemas, no wiring changes | drafted | `2026-05-15-editor-architecture-01-foundation.md` |
| 2 | **Backbone + Curation planners** — replace `run_plan_stage` with two-phase planner producing `list[SectionPlan]` | stub | `2026-05-15-editor-architecture-02-planners.md` |
| 3 | **Research loop** — per-section `query → fetch → research-eval → refine` with global budget cap | stub | `2026-05-15-editor-architecture-03-research-loop.md` |
| 4 | **Block-driven extract** — replace `extract.run` with `BlockSpec`-driven extraction; delete `Module` class | stub | `2026-05-15-editor-architecture-04-extract.md` |
| 5 | **Cleanup** — retire `NeedCurationPlan`, `Module*` schemas, `converter.py`; rename `regen-module` CLI to `regen-section`; update templates | stub | `2026-05-15-editor-architecture-05-cleanup.md` |

---

## Design decisions (locked)

- **6 backbone sections (always on):** `overview`, `key_takeaways`, `timeline`, `background`, `key_facts`, `media_coverage`.
- **Bullet points** are a `ParagraphBlockData.style: "bullets" | "prose"` variant — not a new block kind.
- **Curation is one-shot LLM** (input: triage + tone + already-chosen backbone). No loop at curation layer.
- **Research loop budgets:** `max_iterations=3`, `max_fetch_calls_per_section=4`, global `MAX_TOTAL_TAVILY=30`.
- **Evaluation has three layers:** research-eval (in loop, "enough?") → extraction-eval (post-extract, "correct?") → page-eval (post-assembly, "coherent?").
- **Block kinds stay at 7** (closed enum). Adding `relationship` / `network` is out of scope; revisit if curation proposes it ≥3× across real runs.

---

## Order of execution

Plans must land in order (1 → 5). Plan 1 is purely additive — safe to land with old pipeline untouched. Plan 2 introduces a feature flag (`USE_EDITOR_ARCHITECTURE=1`) that gates the new control flow; Plans 3–4 build behind the flag; Plan 5 removes the flag and the legacy code.
