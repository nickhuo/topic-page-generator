"""Prompt builder for the block-extract LLM call.

For each SectionPlan, we compose:
  BASE_PREAMBLE + spec.extraction_prompt_fragment + section context + evidence

The model's response_format is `spec.data_schema` (a Pydantic block-data
class). The CLI-side stage post-validates citations against the per-section
evidence pool.
"""

from __future__ import annotations

from generator.blocks.specs.base import BlockSpec
from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import SectionPlan, Source


def _format_evidence_block(sources: list[Source]) -> str:
    if not sources:
        return "(no evidence)"
    lines = []
    for s in sources:
        line = (
            f"<src id=\"{s.id}\" tier=\"{s.publisher.tier}\" "
            f"publisher=\"{s.publisher.name}\" "
            f"url=\"{s.url}\" published=\"{s.published_at}\">\n"
            f"  title: {s.title}\n"
            f"  summary: {(s.summary or '')[:480]}\n"
            f"</src>"
        )
        lines.append(line)
    return "\n".join(lines)


def build_block_extract_messages(
    *,
    section: SectionPlan,
    spec: type[BlockSpec],
    sources: list[Source],
    canonical_title: str,
) -> list[dict]:
    evidence_block = _format_evidence_block(sources)
    user = (
        f"CANONICAL_TITLE: {canonical_title}\n"
        f"SECTION_ID: {section.section_id}\n"
        f"SECTION_TITLE: {section.title}\n"
        f"INTENT: {section.intent}\n"
        f"ACCEPTANCE: {section.acceptance.description}\n"
        f"BLOCK_KIND: {section.block_kind}\n"
        f"\n<evidence>\n{evidence_block}\n</evidence>\n"
        f"\nOUTPUT a {section.block_kind} block JSON now."
    )
    return [
        {
            "role": "system",
            "content": (
                BASE_PREAMBLE + "\n\n" + spec.extraction_prompt_fragment
            ),
        },
        {"role": "user", "content": user},
    ]


__all__ = ["build_block_extract_messages"]
