# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Toolchain

Python project managed with `uv`. Never use `pip` or `poetry`. Run `uv sync` after any `pyproject.toml` change; run scripts via `uv run`.

## Commands

```bash
uv sync                                              # install / refresh deps
uv run generate run "<one-sentence event>"           # full pipeline, interactive HITL
uv run generate run --auto "<sentence>"              # bypass HITL, auto-accept
uv run generate run --review-plan "<sentence>"       # add the optional plan-override touchpoint
uv run generate regen-module <kind> output/<slug>.data.json   # re-run Stage 5 for one module

uv run pytest                                        # run tests (asyncio_mode = auto, pythonpath = src)
uv run pytest tests/pipeline/test_triage.py::test_x  # single test
uv run pytest -k "extract and not slow"              # filter

uv run ruff check .                                  # lint
uv run ruff format .                                 # format
```

Required env vars (in `.env` or `.env.local` — `.env.local` overrides): `OPENROUTER_API_KEY`, `TAVILY_API_KEY`. Optional `MODEL_TRIAGE`, `MODEL_DISAMBIGUATE`, `MODEL_AESTHETIC` per-stage model overrides — defaults live in `src/generator/llm/client.py`.

CLI exit codes: `1` LLM config, `2` schema validation, `3` network/fetch, `4` LLM bad output.

## Architecture

The CLI runs an 8-stage async pipeline orchestrated in `src/generator/cli.py::generate`. Each stage is wrapped by `TraceRecorder.stage(...)` (`src/generator/pipeline/trace.py`) which captures model, tokens, cost, duration, retries, and individual LLM calls into the final trace.

Stages and where they live (all under `src/generator/pipeline/`):

1. **triage** — classify event, extract entity / type / temporal posture
2. **disambiguate** — resolve ambiguous entities (Wikidata lookup via `sources/wikidata.py`)
3. **plan** — `run_plan_stage` is an LLM call producing `NeedPlanOutput` (`pipeline/plan.py` + `prompts/plan.py`): for each of the 8 reader needs, the model decides activation, rank, an event-specific H2 (`section_title`), 1–2 Tavily `fetch_queries`, which module kinds to assign, and a `publisher_quota`. `to_legacy_plan_output()` synthesises a `PlanOutput` from this for stages not yet migrated to the needs contract (extract, consistency). `run_aesthetic_stage` then picks one of four palette/typography moods (`product_focus`, `live_dominance`, `imminent_event`, `reference`). The old archetype-table lookup was deleted in the Phase-1 cutover.
4. **fetch** — `run_fetch_stage` fans out one Tavily call per `(need, fetch_query)` in parallel (semaphore-bounded, MAX_TAVILY_CALLS cap), tags each Source with its `serves_needs`, dedupes URLs while merging need attribution, then enriches missing thumbnails/summaries via OpenGraph scrape (`sources/og_scrape.py`, selectolax + httpx). Empty pool raises `EmptyEvidencePoolError`.
5. **extract** — `extract.run` populates each module in parallel; each `Module` subclass under `src/generator/modules/` (hero, infobox, reactions, schedule, comparison, etc.) owns its own Pydantic schema and prompt. `MODULE_REGISTRY` is populated by `all_modules()`. `extract_one_module` is the single-module entry point used by both regen paths.
6. **consistency** — cross-module consistency check, may rewrite/drop modules; produces `needs_coverage` + `uncovered`
7. **render** — `render.build_page` assembles an `EventPage` (now carrying the full `need_plans`); `render.render_html` walks the plan in rank order, calls `blocks.module_to_block()` to adapt each assigned module into one of 7 `RenderBlock` shapes (`paragraph` / `timeline` / `chart` / `newsfeed` / `factsheet` / `map` / `reactions`), and renders a two-column layout (main content + reference sidebar) with a horizontal sticky chip nav above the main column. Templates live under `templates/{chrome,needs,blocks}/`. Hero lives in `templates/chrome/` as page chrome, not inside need sections; the `toc` (horizontal nav), `reference`, `reference_timeline`, and `reference_wikipedia` partials in `templates/chrome/` power the top nav and the right reference sidebar. Citations stay inline (`<span class="citation">`); there is no page-bottom sources card.
8. **deliver** — writes `output/<slug>.{html,data.json,trace.json}`; runs final-approval HITL

**HITL (editor-in-the-loop)** is implemented as `EditorPrompter` in `src/generator/editor/prompt_cli.py`. It is invoked between stages (triage_review, disambiguation_review, plan_review, module_review, final_approval). In `--auto`, every prompt auto-accepts but still records an `EditorAction` with `reason: "auto_mode"`. Module review fires only when `module.confidence.overall < 0.80` or confidence flags are non-empty.

**Schema discipline.** `src/generator/schema.py` is the single source of truth — `EventPage`, `Trace`, `EditorAction`, `Module*`, `Source`, etc. Every LLM call boundary validates with Pydantic; malformed output raises and is retried by `tenacity`. Citations are required on factual claims; unsourced assertions fail validation. **Don't relax these — failures here are the safety property the project is built around.** See `docs/schema.md` for the full contract.

**LLM client.** `src/generator/llm/client.py` wraps OpenRouter via the `openai` SDK with tenacity retries. `LLMConfigError` / `LLMOutputError` are the typed failure modes the CLI maps to exit codes. `llm/trace_buffer.py` is a module-level buffer that captures each call so `TraceRecorder` can attach them to the current stage — `_reset_llm_calls()` is called once at CLI entry.

**Prompts** live in `src/generator/prompts/` (one file per stage that issues an LLM call) and inside each module file under `modules/`. `base_preamble.py` is shared across stages.

**`regen-module` subcommand** reconstructs minimal `PlanOutput` / `AestheticPlanOutput` stubs from a saved `EventPage` so a single module can be re-extracted without rerunning Stages 1–4. (`EventPage.need_plans` is available too if richer reconstruction is needed.) If you add fields that `extract_one_module` reads, update the stub construction in `cli.py::regen_module`.

**Block layer** (`src/generator/blocks/`). `schema.py` defines the 7 `RenderBlock` shapes (`paragraph` / `timeline` / `chart` / `newsfeed` / `factsheet` / `map` / `reactions`) plus primitives (`NewsCard`, `TimelineEntry`, `Location`, `PullQuote`, etc.). `converter.py::module_to_block(module, sources, override)` adapts any `TypedModule` to a `RenderBlock`; templates only consume blocks, never raw module data. The default block kind per module is in `_DEFAULT_BLOCK_KIND`; a `need_plan.render_overrides[module_kind]` wins when set.

## Tests

`tests/` mirrors `src/generator/` plus a top-level `tests/integration/` for end-to-end `--auto` runs with mocked LLM + HTTP (using `respx`). `tests/fixtures.py` and `tests/fixtures/` provide canned LLM responses and source pools. `pythonpath = ["src", "."]` and `asyncio_mode = "auto"` are set in `pyproject.toml`, so `async def` tests need no decorator.

## Domain docs

Single-context: one `CONTEXT.md` at the repo root and ADRs under `docs/adr/` (created lazily by `/grill-with-docs` — don't pre-create). When naming domain concepts, use the vocabulary defined in `CONTEXT.md` if present. See `docs/agents/domain.md`.

## Agent workflow

- Issues live in **Linear**, team `DEV`, project `topic-page-generator`, via the Linear MCP tools. See `docs/agents/issue-tracker.md`.
- Triage uses five canonical labels: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.
- Product framing: `docs/PRD.md`. Design rationale: `docs/DESIGN.md`. Data contract: `docs/schema.md`.
