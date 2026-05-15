"""Stage 5 — Module extraction (parallel, per-kind, need-aware)."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ValidationError

from generator.llm import call_structured, get_default_model, LLMOutputError
from generator.modules import all_modules
from generator.modules.base import Module, PlanContext
from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import (
    AestheticPlanOutput,
    Citation,
    EventSubject,
    NeedCurationPlan,
    NeedPlanOutput,
    Priority,
    Slot,
    Source,
    SourceTier,
    TypedModule,
)

log = logging.getLogger(__name__)
_TIER_RANK: dict[SourceTier, int] = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}

# Default slot assignments when assembling modules. Slot was a layout-grid
# concept that the editorial single-column flow no longer routes on, but the
# field still lives on EventPage.modules for downstream tooling/legacy traces.
_DEFAULT_SLOT_BY_KIND: dict[str, Slot] = {
    "hero": "hero",
    "infobox": "aside",
    "media_coverage": "tail",
}


def _rank_to_priority(rank: int) -> Priority:
    if rank <= 1:
        return "required"
    if rank <= 3:
        return "high"
    if rank <= 5:
        return "medium"
    return "low"


def _plan_for_kind(need_plan: NeedPlanOutput, kind: str) -> NeedCurationPlan | None:
    """Find the activated need plan whose assigned_modules contains this kind."""
    for plan in sorted(need_plan.need_plans, key=lambda p: p.rank):
        if not plan.activated:
            continue
        if kind in plan.assigned_modules:
            return plan
    return None


def _max_time_range_days(need_plan: NeedPlanOutput) -> int:
    """Broadest time window asked for across all activated need queries."""
    days = 14
    for plan in need_plan.need_plans:
        if not plan.activated:
            continue
        for fq in plan.fetch_queries:
            if fq.time_range_days is not None:
                days = max(days, fq.time_range_days)
    return days


def _filter_evidence(pool: list[Source], need_plan: NeedPlanOutput) -> list[Source]:
    """Time-window filter on the source pool.

    Tier filtering used to live here too via PlanOutput.source_strategy; the
    needs-driven fetch already enforces per-need publisher diversity, so this
    only applies a coarse recency window (2× the broadest plan window).
    """
    days = _max_time_range_days(need_plan)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days * 2)
    filtered = [s for s in pool if _parse_iso(s.published_at) >= cutoff]
    return filtered or pool


def _parse_iso(s: str) -> datetime:
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.now(timezone.utc)


def _render_evidence_block(sources: list[Source]) -> str:
    return "\n".join(
        f"[{s.id}] ({s.publisher.tier} {s.publisher.name}, {s.published_at}) "
        f"{s.title} :: {(s.url or '')}"
        for s in sources
    )


def _build_messages(
    module: Module,
    ctx: PlanContext,
    evidence: list[Source],
    *,
    regen_feedback: str | None = None,
) -> list[dict]:
    user = module.extraction_prompt_template.format(
        primary_entity=ctx.subject.primary_entity,
        event_type_hint=ctx.subject.event_type_hint,
        evidence_block=_render_evidence_block(evidence),
    )
    if regen_feedback:
        user += f"\n\nREGEN NOTE: {regen_feedback}\nProduce a corrected JSON output."
    return [
        {"role": "system", "content": BASE_PREAMBLE},
        {"role": "user", "content": user},
    ]


async def extract_one_module(
    module: Module,
    ctx: PlanContext,
    evidence: list[Source],
    *,
    regen_feedback: str | None = None,
) -> TypedModule | None:
    try:
        data = await call_structured(
            model=get_default_model("extract"),
            messages=_build_messages(
                module, ctx, evidence, regen_feedback=regen_feedback
            ),
            response_model=module.data_schema,
        )
    except (LLMOutputError, ValidationError) as exc:
        log.warning("module %s extraction failed: %s", module.kind, exc)
        return None

    if not module.should_render(data):
        return None

    cited_ids = _collect_cited_ids(data)
    pool_ids = {s.id for s in evidence}
    if cited_ids and not cited_ids.issubset(pool_ids):
        log.warning(
            "module %s cited unknown source_ids: %s", module.kind, cited_ids - pool_ids
        )
        return None

    sources_used = [s for s in evidence if s.id in cited_ids]
    confidence = module.confidence(data, sources_used)
    artifact = module.default_artifact(ctx, data)

    return _assemble_typed_module(module, data, sources_used, confidence, artifact, ctx)


def _collect_cited_ids(data: BaseModel) -> set[str]:
    found: set[str] = set()

    def visit(node: Any) -> None:
        if isinstance(node, BaseModel):
            for name, value in node.__dict__.items():
                if name == "source_id" and isinstance(value, str):
                    found.add(value)
                elif name == "citations" and isinstance(value, list):
                    for c in value:
                        if hasattr(c, "source_id"):
                            found.add(c.source_id)
                else:
                    visit(value)
        elif isinstance(node, list):
            for item in node:
                visit(item)
        elif isinstance(node, dict):
            for v in node.values():
                visit(v)

    visit(data)
    return found


def _assemble_typed_module(
    module: Module,
    data: BaseModel,
    sources_used: list[Source],
    confidence,
    artifact: str,
    ctx: PlanContext,
):
    """Wrap an extracted data payload in its TypedModule envelope.

    Slot / priority used to come from PlanOutput.composition; in the needs-
    driven world they're derived from which activated need-plan claims this
    module kind. Falls back to module-kind defaults if no plan claims it.
    """
    plan = _plan_for_kind(ctx.need_plan, module.kind)
    slot: Slot = _DEFAULT_SLOT_BY_KIND.get(module.kind, "primary")
    inclusion_reason: Priority = (
        _rank_to_priority(plan.rank) if plan is not None else "medium"
    )
    citations = _citations_for(data, sources_used)

    cls = _typed_module_class_for(module.kind)
    return cls(
        module_id=f"mod_{module.kind}",
        serves_needs=module.serves_needs,
        citations=citations,
        confidence=confidence,
        slot=slot,
        artifact=artifact,
        artifact_alternatives=[],
        inclusion_reason=inclusion_reason,
        data=data,
    )


def _citations_for(data: BaseModel, sources_used: list[Source]) -> list[Citation]:
    ids = _collect_cited_ids(data)
    return [
        Citation(
            source_id=s.id, claim_text=f"Supporting evidence from {s.publisher.name}."
        )
        for s in sources_used
        if s.id in ids
    ]


def _typed_module_class_for(kind: str):
    from generator.schema import (
        HeroModule,
        InfoboxModule,
        ScheduleModule,
        KPINumbersModule,
        ComparisonModule,
        ChangelogModule,
        ReactionsModule,
        MediaCoverageModule,
        OfficialStatementsModule,
        WhereToWatchModule,
        BackgroundModule,
    )

    return {
        "hero": HeroModule,
        "infobox": InfoboxModule,
        "schedule": ScheduleModule,
        "kpi_numbers": KPINumbersModule,
        "comparison": ComparisonModule,
        "changelog": ChangelogModule,
        "reactions": ReactionsModule,
        "media_coverage": MediaCoverageModule,
        "official_statements": OfficialStatementsModule,
        "where_to_watch": WhereToWatchModule,
        "background": BackgroundModule,
    }[kind]


async def run(
    need_plan: NeedPlanOutput,
    aesthetic: AestheticPlanOutput,
    subject: EventSubject,
    evidence_pool: list[Source],
) -> list[TypedModule]:
    ctx = PlanContext(subject=subject, need_plan=need_plan, aesthetic=aesthetic)
    evidence = _filter_evidence(evidence_pool, need_plan)

    # Union of every assigned_module across activated needs.
    assigned: set[str] = set()
    for plan in need_plan.need_plans:
        if not plan.activated:
            continue
        assigned.update(plan.assigned_modules)
    kinds_to_run = list(assigned) or [m.kind for m in all_modules()]
    modules = [cls() for cls in all_modules() if cls.kind in kinds_to_run]

    results = await asyncio.gather(
        *(extract_one_module(m, ctx, evidence) for m in modules),
        return_exceptions=True,
    )
    out: list[TypedModule] = []
    for r in results:
        if isinstance(r, BaseException):
            log.warning("module dispatch raised: %s", r)
            continue
        if r is not None:
            out.append(r)
    return out
