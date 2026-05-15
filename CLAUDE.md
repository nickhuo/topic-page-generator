# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Toolchain

Python project managed with `uv`. Never use `pip` or `poetry`. Run `uv sync` after any `pyproject.toml` change; run scripts via `uv run`.

## Commands

```bash
uv sync                                              # install / refresh deps
uv run generate run "<one-sentence event>"           # full editor pipeline, interactive HITL
uv run generate run --auto "<sentence>"              # bypass HITL, auto-accept
uv run generate regen-section <section_id> output/<slug>.data.json   # re-extract one section

uv run pytest                                        # run tests (asyncio_mode = auto, pythonpath = src)
uv run pytest tests/pipeline/test_ground.py::test_x  # single test
uv run pytest -k "extract and not slow"              # filter

uv run ruff check .                                  # lint
uv run ruff format .                                 # format
```

Required env vars (in `.env` or `.env.local` — `.env.local` overrides): `OPENROUTER_API_KEY`, `TAVILY_API_KEY`. Optional `BRAVE_API_KEY` — if absent, gallery sections are silently skipped (no crash). Optional `MODEL_GROUND`, `MODEL_CURATION`, `MODEL_RESEARCH_QUERY`, `MODEL_RESEARCH_EVAL`, `MODEL_BLOCK_EXTRACT` per-stage model overrides — defaults live in `src/generator/llm/client.py`.

CLI exit codes: `1` LLM config, `2` schema validation, `3` network/fetch, `4` LLM bad output, `5` not a hot event / user rejected.

## Architecture (editor architecture)

The CLI runs an async editorial pipeline orchestrated in `src/generator/cli.py::generate`. Each stage is wrapped by `TraceRecorder.stage(...)` (`src/generator/pipeline/trace.py`) which captures model, tokens, cost, duration, retries, and individual LLM calls into the final trace.

Stages and where they live (all under `src/generator/pipeline/` unless noted):

1. **ground** (`pipeline/ground.py` + `prompts/ground.py`) — gate + fact extraction in a single LLM call. Tavily search on the raw input sentence (`time_range_days=14`); the LLM decides `is_hot_event` and, if true, extracts `EventFacts` (`entities`, `what`, `when`, `where`, `why`) grounded in the supporting sources. The gate output is `GroundOutput`. Non-hot inputs short-circuit to exit code 5.
2. **curation** — backbone (deterministic, 6 sections via `backbone_planner.py`) + LLM curation (0–4 extra sections via `curation_planner.py` + `prompts/curation.py`). Both consume `EventFacts` + `canonical_title` and produce a combined `SectionPlanOutput`.
3. **research** — per-section research loop (`research.py`, `research_eval.py`, `prompts/research_query.py`, `prompts/research_eval.py`). Budgets: max 3 iterations per section, max 4 Tavily calls per section, MAX_TOTAL_TAVILY=30 globally. Wikidata + Wikipedia card fetched once and prepended to every section's pool.
4. **block_extract** (`block_extract.py`) — extracts one `RenderedSection` per `SectionPlan` using the matching `BlockSpec`. Citation integrity + `is_minimum_viable` gating per section.
5. **render** — `render.build_editorial_page()` + `render.render_html()`. Two-column layout (main content + reference sidebar) with a horizontal sticky chip nav. Templates live under `templates/{chrome,needs,blocks}/`. Citations stay inline (`<span class="citation">`).
6. **deliver** — writes `output/<slug>.{html,data.json,trace.json}`; runs `final_approval` HITL.

**HITL (editor-in-the-loop)** is implemented as `EditorPrompter` in `src/generator/editor/prompt_cli.py`. Active touchpoints: `ground_review` (sentence reformulation / fact edit in `$EDITOR`) and `final_approval` (approve/reject final HTML). In `--auto`, every prompt auto-accepts but still records an `EditorAction` with `reason: "auto_mode"`. Per-section review is planned but not yet wired.

**Schema discipline.** `src/generator/schema.py` is the single source of truth — `EventPage`, `RenderedSection`, `SectionPlan`, `Source`, `Trace`, `EditorAction`, `ResearchEvalResult`, etc. Every LLM call boundary validates with Pydantic; malformed output raises and is retried by `tenacity`. Citations are required on factual claims; unsourced assertions fail validation. **Don't relax these — failures here are the safety property the project is built around.** See `docs/schema.md` for the full contract.

**LLM client.** `src/generator/llm/client.py` wraps OpenRouter via the `openai` SDK with tenacity retries. `LLMConfigError` / `LLMOutputError` are the typed failure modes the CLI maps to exit codes. `llm/trace_buffer.py` is a module-level buffer that captures each call so `TraceRecorder` can attach them to the current stage — `_reset_llm_calls()` is called once at CLI entry.

**Prompts** live in `src/generator/prompts/` (one file per LLM-issuing stage). `base_preamble.py` is shared across stages.

**Block layer** (`src/generator/blocks/`):
- `schema.py` — `RenderBlock` discriminated union (7 kinds: `paragraph` / `timeline` / `chart` / `newsfeed` / `factsheet` / `map` / `reactions`) plus primitives (`NewsCard`, `TimelineEntry`, `Location`, `PullQuote`, etc.).
- `specs/` — `BlockSpec` per kind. Each owns `data_schema`, `extraction_prompt_fragment`, `template_path`, `default_acceptance`, `is_minimum_viable()`. Registry via `get_spec(kind)`.

**`regen-section` subcommand** reconstructs a single `SectionPlan` stub from a saved `EventPage.editorial_sections[i]` and re-runs `block_extract.extract_one_section()` against that section's saved `sources_used`.

## Tests

`tests/` mirrors `src/generator/`. Pipeline unit tests under `tests/pipeline/`, prompt builders under `tests/prompts/`, blocks under `tests/blocks/specs/`, schema under `tests/schema/`, end-to-end + render integration under `tests/integration/`. `tests/fixtures.py` and `tests/fixtures/` provide canned LLM responses and source pools. `pythonpath = ["src", "."]` and `asyncio_mode = "auto"` are set in `pyproject.toml`, so `async def` tests need no decorator.

## Domain docs

Single-context: one `CONTEXT.md` at the repo root and ADRs under `docs/adr/` (created lazily by `/grill-with-docs` — don't pre-create). When naming domain concepts, use the vocabulary defined in `CONTEXT.md` if present. See `docs/agents/domain.md`.

## Agent workflow

- Issues live in **Linear**, team `DEV`, project `topic-page-generator`, via the Linear MCP tools. See `docs/agents/issue-tracker.md`.
- Triage uses five canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.
- Product framing: `docs/PRD.md`. Design rationale: `docs/DESIGN.md`. Data contract: `docs/schema.md`.
