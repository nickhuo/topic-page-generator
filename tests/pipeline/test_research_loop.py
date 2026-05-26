"""Per-section research loop with budget caps."""

from __future__ import annotations

from generator.pipeline.research import (
    DEFAULT_MAX_FETCH_CALLS_PER_SECTION,
    DEFAULT_MAX_ITERATIONS_PER_SECTION,
    DEFAULT_MAX_TOTAL_TAVILY,
    ResearchBudget,
    run_research_stage,
)
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    ResearchEvalResult,
    SectionPlan,
    Source,
    SourceRights,
)


def _section(sid: str = "overview", block: str = "paragraph") -> SectionPlan:
    return SectionPlan(
        section_id=sid,
        kind="backbone",
        title=sid.title(),
        rank=1,
        block_kind=block,  # type: ignore[arg-type]
        intent="i",
        acceptance=AcceptanceCriteria(description="cover the basics"),
    )


def _fake_source(url: str, pub: str = "Reuters") -> Source:
    return Source(
        id="s_" + str(abs(hash(url)))[:6],
        url=url,
        publisher=Publisher(name=pub, tier="T1"),
        title="t",
        published_at="2026-03-19T12:00:00Z",
        fetched_at="2026-03-19T13:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )


def test_default_budgets():
    assert DEFAULT_MAX_ITERATIONS_PER_SECTION == 3
    assert DEFAULT_MAX_FETCH_CALLS_PER_SECTION == 4
    assert DEFAULT_MAX_TOTAL_TAVILY == 50


async def test_loop_exits_when_eval_satisfied_first_iteration(monkeypatch):
    """If eval returns satisfied=True on iteration 1, no refinement happens."""
    call_log: dict[str, int] = {"tavily": 0, "eval": 0, "query": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        call_log["eval"] += 1
        return ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None)

    async def fake_query(**_):
        call_log["query"] += 1
        return "initial query"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr(
        "generator.pipeline.research.run_research_eval_stage", fake_eval
    )
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    result, logs = await run_research_stage(
        sections=[_section()],
        canonical_title="t",
        facts=None,  # not used by fakes
        seed_sources=[],
    )
    assert call_log["query"] == 1
    assert call_log["tavily"] == 1
    assert call_log["eval"] == 1
    assert "overview" in result
    assert result["overview"]
    # The research log captures the single satisfied iteration.
    assert [log.section_id for log in logs] == ["overview"]
    steps = logs[0].steps
    assert len(steps) == 1
    assert steps[0].iteration == 1
    assert steps[0].query
    assert steps[0].eval.satisfied is True


async def test_loop_iterates_when_eval_unsatisfied(monkeypatch):
    """When eval is unsatisfied, the loop refines query and runs again."""
    eval_returns = iter(
        [
            ResearchEvalResult(satisfied=False, gaps=["x"], next_query_hint="more"),
            ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None),
        ]
    )
    call_log = {"tavily": 0, "eval": 0, "query": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        call_log["eval"] += 1
        return next(eval_returns)

    async def fake_query(**_):
        call_log["query"] += 1
        return f"q{call_log['query']}"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr(
        "generator.pipeline.research.run_research_eval_stage", fake_eval
    )
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    await run_research_stage(
        sections=[_section()], canonical_title="t", facts=None, seed_sources=[]
    )
    assert call_log["eval"] == 2
    assert call_log["tavily"] == 2
    assert call_log["query"] == 2  # initial + refine


async def test_loop_respects_max_iterations(monkeypatch):
    """Eval that never returns satisfied still terminates at MAX_ITERATIONS."""
    call_log = {"eval": 0, "tavily": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        call_log["eval"] += 1
        return ResearchEvalResult(
            satisfied=False, gaps=["always more"], next_query_hint="more"
        )

    async def fake_query(**_):
        return "q"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr(
        "generator.pipeline.research.run_research_eval_stage", fake_eval
    )
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    await run_research_stage(
        sections=[_section()],
        canonical_title="t",
        facts=None,
        seed_sources=[],
        budget=ResearchBudget(max_iterations_per_section=2),
    )
    assert call_log["eval"] == 2
    assert call_log["tavily"] == 2


async def test_global_tavily_cap_across_sections(monkeypatch):
    """Sum of Tavily calls across all sections never exceeds budget.max_total_tavily."""
    call_log = {"tavily": 0}

    async def fake_tavily(query, **_):
        call_log["tavily"] += 1
        return [_fake_source(f"https://r.com/{call_log['tavily']}")]

    async def fake_eval(**_):
        return ResearchEvalResult(
            satisfied=False, gaps=["always more"], next_query_hint="m"
        )

    async def fake_query(**_):
        return "q"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr(
        "generator.pipeline.research.run_research_eval_stage", fake_eval
    )
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    # 6 sections, each would naturally want max_iterations=3 → 18 calls; cap at 5.
    sections = [_section(sid=f"s{i}") for i in range(6)]
    await run_research_stage(
        sections=sections,
        canonical_title="t",
        facts=None,
        seed_sources=[],
        budget=ResearchBudget(max_total_tavily=5, max_iterations_per_section=3),
    )
    assert call_log["tavily"] <= 5


async def test_seed_sources_prepended_to_every_section(monkeypatch):
    """Wikidata/Wikipedia seed sources are visible to every section's eval."""
    seen_sources_per_eval: list[list[str]] = []

    async def fake_tavily(query, **_):
        return [_fake_source("https://t.example/x")]

    async def fake_eval(**kwargs):
        seen_sources_per_eval.append([s.id for s in kwargs["sources"]])
        return ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None)

    async def fake_query(**_):
        return "q"

    monkeypatch.setattr("generator.pipeline.research.fetch_tavily", fake_tavily)
    monkeypatch.setattr(
        "generator.pipeline.research.run_research_eval_stage", fake_eval
    )
    monkeypatch.setattr("generator.pipeline.research._gen_query", fake_query)

    seed = [_fake_source("https://wikidata.org/wiki/Q1", pub="Wikidata")]
    seed[0] = seed[0].model_copy(update={"id": "seed1"})

    await run_research_stage(
        sections=[_section("s1"), _section("s2")],
        canonical_title="t",
        facts=None,
        seed_sources=seed,
    )
    assert all("seed1" in ids for ids in seen_sources_per_eval)
