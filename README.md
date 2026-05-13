# Topic Page Generator

Newsbreak take-home: takes a one-sentence event description and produces a
publishable topic page. See [`docs/PRD.md`](./docs/PRD.md),
[`docs/schema.md`](./docs/schema.md), and [`docs/DESIGN.md`](./docs/DESIGN.md).

This branch is **PR 1 of 6** — scaffold only. The pipeline runs end-to-end on
hardcoded mock data and writes an ugly placeholder HTML file. Real LLM calls,
real source fetching, real templates, and the HITL loop arrive in PRs 2–6.

## Setup

```bash
uv sync
cp .env.example .env   # fill in keys later (not needed for PR 1)
```

## Run

```bash
uv run generate "OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT in May 2026"
```

Outputs to `output/`:

- `<slug>.html` — placeholder topic page (open in a browser)
- `<slug>.data.json` — the validated `EventPage` payload
- `<slug>.trace.json` — pipeline trace (stages, timings, outcomes)

`--auto` is the default; `--interactive` exists as a flag but does nothing
this PR.

## Test

```bash
uv run pytest
```
