# Editor Architecture — Plan 3: Per-Section Research Loop (STUB)

> Detailed steps will be written after Plan 2 lands.

**Goal:** For each `SectionPlan` from Plan 2, run a capped `query → fetch → research-eval → refine` loop until acceptance criteria are met or the budget is exhausted.

**Budgets (locked):** `max_iterations=3`, `max_fetch_calls_per_section=4`, global `MAX_TOTAL_TAVILY=30`.

## In scope

1. `src/generator/pipeline/research.py` — `run_research_stage(sections, subject) -> dict[section_id, list[Source]]`. Per-section loop, all sections run in parallel under a global semaphore + Tavily call counter.

2. `src/generator/pipeline/research_eval.py` — LLM judge. Input: section + evidence digest. Output: `ResearchEvalResult(satisfied: bool, gaps: list[str], next_query_hint: str | None)`.

3. `src/generator/prompts/research_query.py` — generates initial query from `SectionPlan.intent` and (on refine) re-generates using `gaps + next_query_hint`.

4. Shared evidence pool: sources fetched for section A also visible to section B during their respective evals (read-only union, dedup by URL preserving `serves_sections` attribution analogous to current `serves_needs`).

5. Wikidata + Wikipedia REST calls happen once (not per-section), prepended to every section's evidence pool.

## Tests

- Unit: research eval LLM mocked to return `satisfied=False` once then `True`; loop exits after 2 iterations.
- Unit: loop respects `max_iterations` (mock always returns `satisfied=False`).
- Unit: global Tavily counter caps total calls across sections.
- Integration: full env-gated path through Plan 2 + Plan 3 with mocked LLM + respx-stubbed Tavily; emits per-section evidence pools.

## Out of scope

- Block extraction (Plan 4).
- Removing old `run_fetch_stage` (Plan 5).
