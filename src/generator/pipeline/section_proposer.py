"""Editor-triggered section proposer.

Invoked from the plan_review HITL gate when the editor types a free-form
description of a new section. Returns a fresh `SectionPlan` (kind="curated",
placement="main") ready to append to the curated list.

Reuses the curation stage's model fallback (`MODEL_CURATION`).
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from generator.llm.client import call_structured, get_default_model
from generator.prompts.section_proposer import build_section_proposer_messages
from generator.schema import (
    AcceptanceCriteria,
    BlockKind,
    EventFacts,
    SectionPlan,
)


class _ProposedSection(BaseModel):
    section_id: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=120)
    block_kind: BlockKind
    intent: str = Field(min_length=1)
    acceptance: AcceptanceCriteria


_BACKBONE_KINDS = {"timeline", "latest_news"}


def _slugify(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return s[:40] or "editor_section"


def _unique_id(candidate: str, taken: set[str]) -> str:
    base = _slugify(candidate)
    if base not in taken:
        return base
    i = 2
    while f"{base}_{i}" in taken:
        i += 1
    return f"{base}_{i}"


async def propose_section(
    description: str,
    *,
    facts: EventFacts,
    canonical_title: str,
    existing_sections: list[SectionPlan],
    model: str | None = None,
) -> SectionPlan:
    """Ask the LLM to turn a free-form editor description into a SectionPlan.

    The returned plan is always `kind="curated"`, `placement="main"`, and has
    `rank = max(existing.rank) + 1` so it slots in after every section the
    planner already produced.
    """
    existing_ids = [s.section_id for s in existing_sections]
    messages = build_section_proposer_messages(
        description=description,
        facts=facts,
        canonical_title=canonical_title,
        existing_section_ids=existing_ids,
    )
    resolved_model = model or get_default_model("curation")
    proposed = await call_structured(
        model=resolved_model,
        messages=messages,
        response_model=_ProposedSection,
    )

    # Defensive overrides — never trust the LLM for these contract fields.
    block_kind: BlockKind = (
        "paragraph" if proposed.block_kind in _BACKBONE_KINDS else proposed.block_kind
    )
    section_id = _unique_id(proposed.section_id, set(existing_ids))
    next_rank = max((s.rank for s in existing_sections), default=0) + 1
    next_rank = min(max(next_rank, 1), 20)

    return SectionPlan(
        section_id=section_id,
        kind="curated",
        title=proposed.title,
        rank=next_rank,
        block_kind=block_kind,
        intent=proposed.intent,
        acceptance=proposed.acceptance,
        placement="main",
    )


__all__ = ["propose_section"]
