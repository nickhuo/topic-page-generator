# Topic Page Generator

Turn a one-sentence news event into a publish-ready topic page — HTML, structured data, and a full audit trace — with an editor in the loop.

The pipeline runs real LLM calls behind Pydantic-validated boundaries, fetches live sources, and records every editorial decision so the chain of custody survives the session.

## Setup

```bash
uv sync
cp .env.example .env   # then edit
```

Required env:

```
OPENROUTER_API_KEY=...
TAVILY_API_KEY=...
BRAVE_API_KEY=...
```

Optional: Per-stage model overrides — `MODEL_GROUND`, `MODEL_CURATION`, `MODEL_RESEARCH_QUERY`, `MODEL_RESEARCH_EVAL`, `MODEL_BLOCK_EXTRACT`. Defaults live in `src/generator/llm/client.py`.

## Usage

### Interactive

The editor-in-the-loop pauses at key touchpoints — currently `ground_review` (reformulate the sentence or edit extracted facts in `$EDITOR`) and `final_approval` (approve or reject the rendered page).

```bash
uv run generate run "Bulgaria wins the 2026 Eurovision Song Contest in Vienna"
```

### Auto mode

Skips every prompt. Editor actions are still recorded with `reason: "auto_mode"` so the trace remains complete.

```bash
uv run generate run --auto "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026"
```

### Regenerate a single section

Re-run block extraction for one section against an existing data file. Useful for iterating on a specific section without re-paying for the full pipeline.

```bash
uv run generate regen-section <section_id> output/<slug>.data.json
```

### Outputs

Written to `output/<slug>.{html,data.json,trace.json}`:

- `<slug>.html` — rendered topic page (two-column editorial layout, sticky chip nav).
- `<slug>.data.json` — validated `EventPage` payload.
- `<slug>.trace.json` — per-stage trace plus the full editor-action log.

### Exit codes

| Code | Meaning |
|------|---------|
| `1`  | LLM config error (missing key, bad model name) |
| `2`  | Schema validation failure |
| `3`  | Network / fetch error |
| `4`  | LLM produced unrecoverable bad output |
| `5`  | Not a hot event, or editor rejected the page |

## Architecture

Six stages, each wrapped by `TraceRecorder.stage(...)` so model, token counts, cost, duration, retries, and individual LLM calls are captured per stage:

1. **ground** — Tavily search on the raw sentence (14-day window); a single LLM call gates `is_hot_event` and, if true, extracts `EventFacts` (entities, what, when, where, why) grounded in the supporting sources. Non-hot inputs short-circuit to exit 5.
2. **curation** — Deterministic six-section backbone plus 0–4 extra sections proposed by the curation LLM. Output is a single combined `SectionPlanOutput`.
3. **research** — Per-section research loop with hard budgets (3 iterations, 4 Tavily calls per section; 50 Tavily calls globally). A Wikidata + Wikipedia card is fetched once and prepended to every section's source pool.
4. **block_extract** — One `RenderedSection` per `SectionPlan`, extracted via the matching `BlockSpec`. Citation integrity and an `is_minimum_viable` check gate each section.
5. **render** — `render.build_editorial_page()` + Jinja templates under `templates/{chrome,needs,blocks}/`. Two-column layout, horizontal sticky chip nav, inline citations.
6. **deliver** — Writes the three output files; runs the `final_approval` HITL touchpoint.

`src/generator/schema.py` is the single source of truth for the data contract — `EventPage`, `RenderedSection`, `SectionPlan`, `Source`, `Trace`, `EditorAction`, etc. Every LLM call validates with Pydantic; malformed output raises and is retried by `tenacity`. Unsourced factual claims fail validation. See [`docs/schema.md`](docs/schema.md) for the full contract and [`docs/DESIGN.md`](docs/DESIGN.md) for the design rationale.

## Block layer

Sections are rendered as typed `RenderBlock`s — a discriminated union of `paragraph`, `timeline`, `chart`, `newsfeed`, `reactions`, and `gallery`. Each kind owns a `BlockSpec` in `src/generator/blocks/specs/` that bundles its `data_schema`, extraction prompt fragment, template path, and minimum-viability check. `timeline` is sidebar-only and emitted exclusively by the backbone planner.

## Reading the trace

`<slug>.trace.json` has three top-level fields:

- `pipeline_trace[]` — one entry per stage (model, tokens, cost, duration, outcome, retries, LLM calls).
- `editor_actions[]` — every editor decision (accept, edit, skip, approve, reject) with timestamp and reason. `reason: "auto_mode"` entries are produced by `--auto`.
- `approval` — `auto_mode` flag and `final_outcome` ∈ {`approved_published`, `auto_approved`, `rejected`, `draft_saved`}.

## Tests

```bash
uv run pytest                                  # full suite
uv run pytest tests/pipeline/test_ground.py    # one file
uv run pytest -k "extract and not slow"        # filter
```

`pythonpath = ["src", "."]` and `asyncio_mode = "auto"` are set in `pyproject.toml`, so `async def` tests need no decorator.

## Toolchain

`uv` only — no `pip`, no `poetry`. Run `uv sync` after any `pyproject.toml` change; run scripts via `uv run`. Lint and format with `uv run ruff check .` and `uv run ruff format .`.
