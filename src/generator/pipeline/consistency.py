"""Stage 6 — cross-module consistency + needs coverage."""

from __future__ import annotations

import logging
from typing import Iterable

from generator.llm import call_structured, get_default_model, LLMOutputError
from generator.modules import MODULE_REGISTRY, all_modules
from generator.modules.base import PlanContext
from generator.pipeline.extract import extract_one_module
from generator.prompts.consistency import build_consistency_messages
from generator.schema import (
    ConsistencyCheckOutput,
    NeedId,
    Source,
    TypedModule,
)

log = logging.getLogger(__name__)
MAX_PAGE_REGENS = 2

_ALL_NEEDS: tuple[NeedId, ...] = (
    "what_happened",
    "when_where",
    "who_involved",
    "current_state",
    "why_matters",
    "world_reaction",
    "what_can_do",
    "what_next",
)


async def _consistency_call(modules: list[TypedModule]) -> ConsistencyCheckOutput:
    try:
        return await call_structured(
            model=get_default_model("consistency"),
            messages=build_consistency_messages(modules),
            response_model=ConsistencyCheckOutput,
        )
    except LLMOutputError as exc:
        log.warning("consistency LLM failed; defaulting to passes=true: %s", exc)
        return ConsistencyCheckOutput(passes=True, issues=[])


async def run(
    modules: list[TypedModule],
    ctx: PlanContext,
    evidence_pool: list[Source],
) -> tuple[ConsistencyCheckOutput, list[TypedModule], dict, list]:
    # Ensure all module subclasses are registered before looking up by kind.
    all_modules()
    regens_used = 0
    current = list(modules)

    result = await _consistency_call(current)
    while not result.passes and regens_used < MAX_PAGE_REGENS:
        kinds_to_regen: list[tuple[str, str]] = []
        kinds_to_remove: set[str] = set()
        for issue in result.issues:
            if issue.recommended_action == "regenerate":
                kinds_to_regen.append((issue.module_kind, issue.description))
            elif issue.recommended_action == "remove":
                kinds_to_remove.add(issue.module_kind)

        current = [m for m in current if m.kind not in kinds_to_remove]

        for kind, feedback in kinds_to_regen:
            if kind not in MODULE_REGISTRY:
                continue
            module_inst = MODULE_REGISTRY[kind]()
            new = await extract_one_module(
                module_inst, ctx, evidence_pool, regen_feedback=feedback
            )
            current = [m for m in current if m.kind != kind]
            if new is not None:
                current.append(new)

        regens_used += 1
        result = await _consistency_call(current)

    current = [_flag_reactions_sentiment(m) for m in current]
    needs_coverage, uncovered = _compute_needs_coverage(current)
    return result, current, needs_coverage, uncovered


def _flag_reactions_sentiment(module: TypedModule) -> TypedModule:
    """Flag reactions modules whose cards span fewer than 2 distinct sentiments.

    The Perspectives UI needs at least two sentiment groups to render tabs; a
    single-sentiment block degrades to a flat list. Surface this as a soft
    confidence flag so the editor HITL can decide whether to regenerate.
    """
    if module.kind != "reactions":
        return module
    sentiments = {
        item.sentiment for item in module.data.items if item.sentiment is not None
    }
    if len(sentiments) >= 2:
        return module
    if "single_sentiment_perspective" in module.confidence.flags:
        return module
    new_confidence = module.confidence.model_copy(
        update={
            "flags": [*module.confidence.flags, "single_sentiment_perspective"],
        }
    )
    return module.model_copy(update={"confidence": new_confidence})


def _compute_needs_coverage(
    modules: Iterable[TypedModule],
) -> tuple[dict[NeedId, list[str]], list[NeedId]]:
    coverage: dict[NeedId, list[str]] = {n: [] for n in _ALL_NEEDS}
    for m in modules:
        for need in m.serves_needs:
            coverage[need].append(m.module_id)
    uncovered = [n for n, ids in coverage.items() if not ids]
    return coverage, uncovered
