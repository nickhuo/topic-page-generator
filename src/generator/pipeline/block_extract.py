"""Block-driven extraction: one RenderedSection per SectionPlan.

Replaces the legacy Module-driven extract.py for the editor-architecture
path. Per-section:
  1. Lookup BlockSpec by block_kind.
  2. Compose prompt: BASE_PREAMBLE + spec.extraction_prompt_fragment + section
     context + evidence block.
  3. LLM call with response_model = spec.data_schema.
  4. Post-validate citations against the evidence pool. Drop section if any
     cited source_id is unknown.
  5. Apply spec.is_minimum_viable(); drop if False.
  6. Return RenderedSection(section_id, block_kind, block_data, citations,
     sources_used, eval_passed=True).
"""

from __future__ import annotations

import asyncio
import logging

from generator.blocks.specs import get_spec
from generator.llm.client import call_structured, get_default_model
from generator.prompts.block_extract import build_block_extract_messages
from generator.schema import (
    Citation,
    RenderedSection,
    SectionPlan,
    Source,
)
from generator.sources.brave import (
    BraveConfigError,
    BraveImageResult,
    fetch_brave_images,
)

logger = logging.getLogger(__name__)

# Minimum number of Brave image results required to proceed with gallery extraction.
# Gallery spec requires ≥2 images; we want headroom for the LLM to pick from.
_GALLERY_MIN_IMAGES = 3


def _brave_query_for_section(section: SectionPlan, canonical_title: str) -> str:
    """Build a Brave image search query for a gallery section.

    Uses the section_id for semantic hints (e.g. "stadium_photos") combined
    with the canonical_title. Truncated to ~80 chars.
    """
    raw = f"{canonical_title} {section.intent}"
    return raw[:80]


def _collect_cited_ids(obj) -> set[str]:
    """Recursive walker — find every source_id reference in a block_data tree."""
    cited: set[str] = set()
    if hasattr(obj, "model_dump"):
        obj = obj.model_dump()
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "source_id" and isinstance(v, str):
                cited.add(v)
            else:
                cited |= _collect_cited_ids(v)
    elif isinstance(obj, list):
        for item in obj:
            cited |= _collect_cited_ids(item)
    return cited


async def extract_one_section(
    *,
    section: SectionPlan,
    sources: list[Source],
    canonical_title: str,
    model: str | None = None,
) -> RenderedSection | None:
    spec_cls = get_spec(section.block_kind)
    spec = spec_cls()

    # Gallery sections require Brave image search before LLM extraction.
    image_manifest: list[BraveImageResult] | None = None
    if section.block_kind == "gallery":
        query = _brave_query_for_section(section, canonical_title)
        try:
            results = await fetch_brave_images(query, count=12)
        except BraveConfigError as exc:
            logger.warning(
                "block_extract: dropping gallery section %s — Brave not configured: %s. "
                "Set BRAVE_API_KEY to enable gallery sections.",
                section.section_id,
                exc,
            )
            return None
        if len(results) < _GALLERY_MIN_IMAGES:
            logger.info(
                "block_extract: dropping gallery section %s — only %d Brave results "
                "(need ≥%d for LLM headroom)",
                section.section_id,
                len(results),
                _GALLERY_MIN_IMAGES,
            )
            return None
        image_manifest = results

    messages = build_block_extract_messages(
        section=section,
        spec=spec_cls,
        sources=sources,
        canonical_title=canonical_title,
        image_manifest=image_manifest,
    )
    resolved_model = model or get_default_model("block_extract")
    try:
        data = await call_structured(
            model=resolved_model,
            messages=messages,
            response_model=spec.data_schema,
        )
    except Exception as exc:
        logger.warning("block_extract failed for %s: %s", section.section_id, exc)
        return None

    # Spec-defined normalization (filter/sort/cap items) before integrity checks.
    data = spec.postprocess(data)

    # Citation integrity: every cited source_id must be in the pool.
    pool_ids = {s.id for s in sources}
    cited_ids = _collect_cited_ids(data)
    unknown = cited_ids - pool_ids
    if unknown:
        logger.warning(
            "block_extract dropped %s: cites unknown source_ids %s",
            section.section_id,
            unknown,
        )
        return None

    if not spec.is_minimum_viable(data):
        logger.info(
            "block_extract dropped %s: is_minimum_viable=False", section.section_id
        )
        return None

    sources_by_id = {s.id: s for s in sources}
    citations = [
        Citation(
            source_id=cid,
            claim_text=f"Supporting evidence from {sources_by_id[cid].publisher.name}.",
        )
        for cid in sorted(cited_ids)
        if cid in sources_by_id
    ]
    sources_used = [s for s in sources if s.id in cited_ids]

    return RenderedSection(
        section_id=section.section_id,
        block_kind=section.block_kind,
        block_data=data,
        citations=citations,
        sources_used=sources_used,
        eval_passed=True,
        eval_notes=None,
        placement=section.placement,
    )


async def run_block_extract_stage(
    *,
    sections: list[SectionPlan],
    evidence_by_section: dict[str, list[Source]],
    canonical_title: str,
) -> list[RenderedSection]:
    """Extract all sections in parallel. Dropped sections are filtered out."""
    coros = [
        extract_one_section(
            section=s,
            sources=evidence_by_section.get(s.section_id, []),
            canonical_title=canonical_title,
        )
        for s in sections
    ]
    results = await asyncio.gather(*coros, return_exceptions=True)
    out: list[RenderedSection] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("block_extract task raised: %s", r)
            continue
        if r is not None:
            out.append(r)
    return out


__all__ = ["extract_one_section", "run_block_extract_stage"]
