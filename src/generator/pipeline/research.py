"""Per-section research loop with capped budgets.

Public surface:
- `run_research_stage(sections, canonical_title, facts, seed_sources, budget?)`
  → (dict[section_id, list[Source]], list[SectionResearchLog])
- `ResearchBudget` dataclass (overridable via env vars or kwargs)

The loop runs all sections in parallel under a shared `GlobalBudget` that
tracks total Tavily calls. Per-section, each iteration:
  1. Generate query (or refine using previous gaps)
  2. fetch_tavily(query) → sources
  3. Evaluate pool; if satisfied → exit; else → next iteration

Seed sources (Wikidata + Wikipedia, fetched once at stage start) are
prepended to every section's pool so the eval and the downstream extractor
always see them.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass

from generator.editor.notes import merge_note
from generator.llm.client import call_structured, get_default_model
from generator.pipeline.reporter import NullReporter, PipelineReporter
from generator.pipeline.research_eval import run_research_eval_stage
from generator.prompts.research_query import build_research_query_messages
from generator.schema import (
    EditorNotes,
    EventFacts,
    SectionPlan,
    SectionResearchLog,
    SectionResearchStep,
    Source,
)
from generator.sources.tavily import fetch_tavily

DEFAULT_MAX_ITERATIONS_PER_SECTION = 3
DEFAULT_MAX_FETCH_CALLS_PER_SECTION = 4
DEFAULT_MAX_TOTAL_TAVILY = 50


@dataclass
class ResearchBudget:
    max_iterations_per_section: int = DEFAULT_MAX_ITERATIONS_PER_SECTION
    max_fetch_calls_per_section: int = DEFAULT_MAX_FETCH_CALLS_PER_SECTION
    max_total_tavily: int = DEFAULT_MAX_TOTAL_TAVILY

    @classmethod
    def from_env(cls) -> ResearchBudget:
        return cls(
            max_iterations_per_section=int(
                os.getenv(
                    "MAX_ITERATIONS_PER_SECTION", DEFAULT_MAX_ITERATIONS_PER_SECTION
                )
            ),
            max_fetch_calls_per_section=int(
                os.getenv(
                    "MAX_FETCH_CALLS_PER_SECTION", DEFAULT_MAX_FETCH_CALLS_PER_SECTION
                )
            ),
            max_total_tavily=int(
                os.getenv("MAX_TOTAL_TAVILY", DEFAULT_MAX_TOTAL_TAVILY)
            ),
        )


class _GlobalCounter:
    """Async-safe global Tavily call counter."""

    def __init__(self, cap: int) -> None:
        self._cap = cap
        self._used = 0
        self._lock = asyncio.Lock()

    async def reserve(self) -> bool:
        async with self._lock:
            if self._used >= self._cap:
                return False
            self._used += 1
            return True


async def _gen_query(
    *,
    facts: EventFacts | None,
    canonical_title: str,
    section: SectionPlan,
    previous_gaps: list[str] | None,
    previous_query: str | None,
    editor_note: str | None = None,
    model: str | None = None,
) -> str:
    """Generate (or refine) one Tavily query via the research-query LLM call."""
    if facts is None:
        # Tests sometimes pass facts=None — fall back to the section intent.
        return section.intent
    messages = build_research_query_messages(
        facts=facts,
        canonical_title=canonical_title,
        section=section,
        previous_gaps=previous_gaps,
        previous_query=previous_query,
        editor_note=editor_note,
    )
    from pydantic import BaseModel, Field

    class _QueryOut(BaseModel):
        query: str = Field(min_length=1, max_length=200)

    resolved = model or get_default_model("research_query")
    out = await call_structured(
        model=resolved, messages=messages, response_model=_QueryOut
    )
    return out.query


async def _section_loop(
    *,
    section: SectionPlan,
    canonical_title: str,
    facts: EventFacts | None,
    seed_sources: list[Source],
    budget: ResearchBudget,
    global_counter: _GlobalCounter,
    primary_entity: str,
    reporter: PipelineReporter,
    editor_note: str | None = None,
) -> tuple[list[Source], SectionResearchLog]:
    pool: list[Source] = list(seed_sources)  # always start with seeds
    previous_gaps: list[str] | None = None
    previous_query: str | None = None
    fetch_calls_this_section = 0
    steps: list[SectionResearchStep] = []

    for iter_idx in range(budget.max_iterations_per_section):
        if fetch_calls_this_section >= budget.max_fetch_calls_per_section:
            break
        if not await global_counter.reserve():
            reporter.section_event(section.section_id, "cap_hit")
            break  # global cap hit; stop trying

        query = await _gen_query(
            facts=facts,
            canonical_title=canonical_title,
            section=section,
            previous_gaps=previous_gaps,
            previous_query=previous_query,
            editor_note=editor_note,
        )
        reporter.section_event(
            section.section_id,
            "query_generated",
            iter=iter_idx + 1,
            query=query[:60],
        )
        new_sources = await fetch_tavily(
            query=query,
            time_range_days=14,
            max_results=8,
            primary_entity=primary_entity,
        )
        fetch_calls_this_section += 1

        # Tag with section attribution and merge into pool (dedupe by URL).
        urls_seen = {str(s.url): s for s in pool}
        for s in new_sources:
            tagged = s.model_copy(update={"serves_sections": [section.section_id]})
            url_key = str(tagged.url)
            if url_key in urls_seen:
                # Merge serves_sections lists.
                existing = urls_seen[url_key]
                merged = sorted(set(existing.serves_sections) | {section.section_id})
                urls_seen[url_key] = existing.model_copy(
                    update={"serves_sections": merged}
                )
            else:
                urls_seen[url_key] = tagged
        prev_size = len(pool)
        pool = list(urls_seen.values())
        reporter.section_event(
            section.section_id,
            "pool_grew",
            new=len(pool) - prev_size,
            total=len(pool),
        )

        eval_result = await run_research_eval_stage(
            section=section, sources=pool, canonical_title=canonical_title
        )
        steps.append(
            SectionResearchStep(
                iteration=iter_idx + 1,
                query=query,
                pool_size=len(pool),
                eval=eval_result,
            )
        )
        if eval_result.satisfied:
            reporter.section_event(section.section_id, "eval_satisfied")
            return pool, SectionResearchLog(section_id=section.section_id, steps=steps)
        reporter.section_event(section.section_id, "eval_gaps", gaps=eval_result.gaps)
        previous_gaps = eval_result.gaps
        previous_query = query

    return pool, SectionResearchLog(section_id=section.section_id, steps=steps)


async def run_research_stage(
    *,
    sections: list[SectionPlan],
    canonical_title: str,
    facts: EventFacts | None,
    seed_sources: list[Source],
    budget: ResearchBudget | None = None,
    reporter: PipelineReporter | None = None,
    notes: EditorNotes | None = None,
) -> tuple[dict[str, list[Source]], list[SectionResearchLog]]:
    """Run the per-section research loop in parallel under a global budget.

    Returns the per-section evidence pools plus a per-section research log
    (query + eval iterations) for the trace.
    """
    b = budget or ResearchBudget.from_env()
    global_counter = _GlobalCounter(b.max_total_tavily)
    r = reporter or NullReporter()

    primary_entity = facts.entities[0] if facts and facts.entities else ""

    coros = [
        _section_loop(
            section=s,
            canonical_title=canonical_title,
            facts=facts,
            seed_sources=seed_sources,
            budget=b,
            global_counter=global_counter,
            primary_entity=primary_entity,
            reporter=r,
            editor_note=merge_note(s.section_id, notes),
        )
        for s in sections
    ]
    results = await asyncio.gather(*coros)
    pools = {s.section_id: pool for s, (pool, _log) in zip(sections, results)}
    logs = [log for _pool, log in results]
    return pools, logs


__all__ = [
    "ResearchBudget",
    "run_research_stage",
    "DEFAULT_MAX_ITERATIONS_PER_SECTION",
    "DEFAULT_MAX_FETCH_CALLS_PER_SECTION",
    "DEFAULT_MAX_TOTAL_TAVILY",
]
