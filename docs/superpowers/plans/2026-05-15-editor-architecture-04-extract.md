# Editor Architecture — Plan 4: Block-Driven Extraction (STUB)

> Detailed steps will be written after Plan 3 lands.

**Goal:** Replace `extract.run` (Module-driven) with a BlockSpec-driven extractor. Each section's per-section evidence pool (from Plan 3) is fed into the spec's prompt fragment + the section's intent/acceptance, producing a `RenderedSection`.

## In scope

1. `src/generator/pipeline/block_extract.py` — `run_block_extract(sections, evidence_by_section) -> list[RenderedSection]`. Parallel per section.

2. Per-section extraction prompt composition: `BASE_PREAMBLE + spec.extraction_prompt_fragment + section.intent + section.acceptance.description + evidence_block`.

3. Extraction-eval: reuse the existing post-extract checks from `extract.py` (`_collect_cited_ids` ensures every cited `source_id` is in the section's evidence pool; `is_minimum_viable` from the spec gates the result).

4. Adapt `render.build_page` / `render.render_html` to walk `list[RenderedSection]` instead of `EventPage.modules`. Add a `RenderedSection` field to `EventPage` (or wrap in a new `EditorialPage` schema if it gets messy — decide during planning).

5. Re-route `templates/needs/section.html` to consume `RenderedSection` (block_data + citations). Templates per block kind don't change — they already consume `RenderBlock`.

## Tests

- Unit: extraction of a `paragraph` section with mocked LLM produces a valid `RenderedSection`; cited source_id not in pool → section dropped.
- Unit: `is_minimum_viable=False` from spec → section dropped.
- Integration: env-gated path Plan 2+3+4 produces a fully rendered HTML page from sample event input.
- Snapshot: rendered HTML for a fixture event matches expected output (sections in rank order, citations inline).

## Out of scope

- Deleting old `Module`, `extract.py`, `converter.py` — Plan 5.
