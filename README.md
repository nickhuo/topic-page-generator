# Topic Page Generator

## What this is

Newsbreak topic-page-generator: a CLI that takes one sentence describing a news event and emits a publish-ready topic page (HTML + structured data + audit trace), with an editor-in-the-loop for safety. It runs an 8-stage pipeline backed by real LLM calls, live source fetching, and Pydantic-enforced schemas at every step. Every editor decision is recorded in the trace so the full editorial chain of custody is preserved.

## Setup

```bash
uv sync                            # install deps
cp .env.example .env               # then edit
# Required env vars:
#   OPENROUTER_API_KEY=...
#   TAVILY_API_KEY=...
```

## Usage

### Interactive (default)

The HITL loop pauses after each module so you can accept, regenerate, edit, or skip before the page is published.

```bash
uv run generate run "GPT-5.5 Instant rolls out to all ChatGPT users on May 14, 2026"
```

### Auto mode (bypass HITL)

Accepts all module defaults without pausing. Editor actions are still logged with `reason: "auto_mode"`.

```bash
uv run generate run --auto "The 2026 FIFA World Cup kicks off at Estadio Azteca on June 11, 2026"
```

### Per-module regen

Re-run a single module against an existing data file without re-running the full pipeline.

```bash
uv run generate regen-module reactions output/gpt55-instant.data.json
```

> **Breaking change:** `generate "..."` was the old syntax. With the new subcommand structure it is now `generate run "..."`. The bare invocation no longer works.

Outputs to `output/`:

- `<slug>.html` — rendered topic page
- `<slug>.data.json` — validated `EventPage` payload
- `<slug>.trace.json` — full pipeline and editorial trace

## The demos

- [`output/gpt55-instant.html`](output/gpt55-instant.html) — GPT-5.5 Instant rollout (product launch — `product_focus` preset).
- [`output/eurovision-2026.html`](output/eurovision-2026.html) — Eurovision 2026 in Vienna (live event — `live_dominance` preset).
- [`output/worldcup-2026.html`](output/worldcup-2026.html) — 2026 FIFA World Cup kickoff (scheduled future — `imminent_event` preset).
- [`output/trump-china-visit.html`](output/trump-china-visit.html) — generic event (`reference` fallback preset).

## How to read the trace

Each `<slug>.trace.json` file has three top-level fields. `pipeline_trace[]` contains one entry per pipeline stage, recording the model used, token counts, cost, duration, outcome, retry count, and individual LLM calls. `editor_actions[]` records every editor decision — accept, regen, edit, skip, override, approve, or reject — with a timestamp and a reason string; entries with `reason: "auto_mode"` are the automatic accept-defaults produced by `--auto`. `approval.auto_mode` is a boolean and `final_outcome` is one of `approved_published`, `auto_approved`, `rejected`, or `draft_saved`. See `docs/schema.md` §5 for the full schema.

## Architecture at a glance

The pipeline runs eight stages in order: Triage, Disambiguate, Plan + Aesthetic, Fetch evidence, Extract modules, Consistency check, Render, and Trace. Pydantic schemas are enforced at every LLM call boundary so malformed output is caught and retried immediately rather than propagating silently. Every factual claim requires a citation; unsourced assertions fail validation. The aesthetic layer selects one of four named presets (`product_focus`, `live_dominance`, `imminent_event`, `reference`) based on triage signals, controlling layout, artifact mix, and visual tone. All editor decisions are written to the trace so the editorial chain of custody survives the session. Read `docs/PRD.md` for product framing, `docs/DESIGN.md` for design rationale, and `docs/schema.md` for the data contract.

## Screenshot

![Rendered topic page](docs/screenshot.png)
