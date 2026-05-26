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
from generator.editor.notes import merge_note
from generator.llm.client import call_structured, get_default_model
from generator.pipeline.reporter import NullReporter, PipelineReporter
from generator.prompts.block_extract import build_block_extract_messages
from generator.schema import (
    Citation,
    EditorNotes,
    RenderedSection,
    SectionPlan,
    Source,
)
from generator.sources.brave import (
    BraveConfigError,
    BraveImageResult,
    fetch_brave_images,
)
from generator.sources.og_image import enrich_news_card_thumbnails, enrich_thumbnails
from generator.sources.wikipedia import fetch_wikipedia_card

logger = logging.getLogger(__name__)

# Minimum number of Brave image results required to proceed with gallery extraction.
# Gallery spec requires ≥2 images; we want headroom for the LLM to pick from.
_GALLERY_MIN_IMAGES = 3


class PersonImage:
    """One resolved person image: source-of-record + thumbnail + profile URL.

    Used to build the PEOPLE_IMAGE_MANIFEST / AUTHOR_IMAGE_MANIFEST injected
    above the evidence block so the LLM never invents image URLs.
    """

    __slots__ = ("name", "image_url", "profile_url", "image_source")

    def __init__(
        self,
        *,
        name: str,
        image_url: str,
        profile_url: str | None,
        image_source: str,
    ):
        self.name = name
        self.image_url = image_url
        self.profile_url = profile_url
        self.image_source = image_source


async def _resolve_person_image(name: str) -> PersonImage | None:
    """Try Wikipedia first; fall back to Brave image search.

    People sections are explicitly curated — headline performers, decision
    makers, named principals — so a Brave first-result for "<name> portrait"
    is acceptable when Wikipedia has no thumbnail. Returns None when both
    miss or Brave isn't configured.
    """
    card = await fetch_wikipedia_card(name)
    if card is not None and card.thumbnail_url is not None:
        return PersonImage(
            name=name,
            image_url=str(card.thumbnail_url),
            profile_url=str(card.article_url) if card.article_url else None,
            image_source="wikipedia",
        )
    try:
        results = await fetch_brave_images(f"{name} portrait", count=3)
    except BraveConfigError:
        return None
    except Exception as exc:  # network / parse errors — silent miss
        logger.debug("brave fallback failed for %s: %s", name, exc)
        return None
    if not results:
        return None
    pick = results[0]
    return PersonImage(
        name=name,
        image_url=str(pick.image_url),
        profile_url=str(pick.source_url) if pick.source_url else None,
        image_source="brave",
    )


async def _resolve_person_manifest(names: list[str]) -> list[PersonImage]:
    """Resolve a parallel batch of names; drop entries with no portrait."""
    if not names:
        return []
    coros = [_resolve_person_image(n) for n in names]
    results = await asyncio.gather(*coros, return_exceptions=True)
    manifest: list[PersonImage] = []
    for r in results:
        if isinstance(r, Exception):
            continue
        if r is not None:
            manifest.append(r)
    return manifest


def _brave_query_for_section(section: SectionPlan, canonical_title: str) -> str:
    """Build a Brave image search query for a gallery section.

    Uses the section_id for semantic hints (e.g. "stadium_photos") combined
    with the canonical_title. Truncated to ~80 chars.
    """
    raw = f"{canonical_title} {section.intent}"
    return raw[:80]


def _match_source_by_url(raw_url: str, sources_by_len: list[Source]) -> Source | None:
    """Find the pool source whose URL is the clean prefix of a card URL.

    The block-extract LLM occasionally fails to terminate the copied `url`
    string, leaving the clean article URL with trailing junk appended (`',`,
    `/published_at`, or whole collapsed JSON fields). Since the real URL is
    always a prefix, we match against the evidence pool. `sources_by_len` must
    be sorted longest-URL-first so we never match a shorter prefix belonging to
    a different article on the same host.
    """
    for s in sources_by_len:
        su = str(s.url)
        if raw_url == su or raw_url.startswith(su):
            return s
    return None


def _canonicalize_news_cards(cards: list, sources: list[Source]) -> list:
    """Rebuild each NewsCard's authoritative fields from the matched pool Source.

    Repairs LLM-corrupted `url` values (and stale publisher/tier/date/thumbnail)
    by keying off a longest-prefix URL match against the evidence pool. The
    LLM-written `summary` is preserved; everything else comes from the Source.
    Cards with no pool match pass through unchanged — they get dropped later by
    citation-integrity / viability checks.
    """
    if not cards or not sources:
        return cards
    by_len = sorted(sources, key=lambda s: len(str(s.url)), reverse=True)
    out: list = []
    changed = False
    for c in cards:
        match = _match_source_by_url(str(c.url), by_len)
        if match is None:
            out.append(c)
            continue
        new_c = c.model_copy(
            update={
                "url": match.url,
                "publisher": match.publisher.name,
                "tier": match.publisher.tier,
                "published_at": match.published_at,
                # may be None -> refilled (latest_news) or dropped (newsfeed) downstream
                "thumbnail_url": match.thumbnail_url,
                "source_id": match.id,
            }
        )
        out.append(new_c)
        changed = changed or new_c != c
    return out if changed else cards


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
    entities: list[str] | None = None,
    model: str | None = None,
    reporter: PipelineReporter | None = None,
    editor_note: str | None = None,
) -> RenderedSection | None:
    r = reporter or NullReporter()
    r.section_event(section.section_id, "extract_started", kind=section.block_kind)
    spec_cls = get_spec(section.block_kind)
    spec = spec_cls()

    # Newsfeed sections render image-only cards. Tavily's per-query image
    # pool can't be mapped to individual articles by host (CDN-hosted media,
    # third-party images), so we enrich each source's thumbnail_url here by
    # parsing the article's <meta property="og:image"> tag. Failures are
    # silent — image-less sources just won't appear in the final cards.
    if section.block_kind == "newsfeed":
        await enrich_thumbnails(sources)

    # Person manifest: pre-resolve Wikipedia portraits for people + reactions
    # so the LLM never invents image URLs.
    people_manifest: list[PersonImage] | None = None
    if section.block_kind in ("people", "reactions") and entities:
        people_manifest = await _resolve_person_manifest(entities)
        if section.block_kind == "people" and not people_manifest:
            # Allow people sections without images — bio + role still informative.
            people_manifest = []

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
            r.section_event(
                section.section_id,
                "extract_dropped",
                reason="brave_not_configured",
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
            r.section_event(
                section.section_id,
                "extract_dropped",
                reason="gallery_insufficient_images",
                got=len(results),
                need=_GALLERY_MIN_IMAGES,
            )
            return None
        image_manifest = results

    messages = build_block_extract_messages(
        section=section,
        spec=spec_cls,
        sources=sources,
        canonical_title=canonical_title,
        image_manifest=image_manifest,
        people_manifest=people_manifest,
        editor_note=editor_note,
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
        r.section_event(
            section.section_id,
            "extract_dropped",
            reason="llm_error",
            error=str(exc)[:120],
        )
        return None

    # Repair LLM-corrupted news card URLs against the evidence pool before any
    # downstream filtering / thumbnail enrichment operates on them.
    if section.block_kind in ("newsfeed", "latest_news") and getattr(
        data, "cards", None
    ):
        canon = _canonicalize_news_cards(list(data.cards), sources)
        if canon != list(data.cards):
            data = data.model_copy(update={"cards": canon})

    # Spec-defined normalization (filter/sort/cap items) before integrity checks.
    data = spec.postprocess(data)

    # Post-extract image enrichment.
    if section.block_kind == "latest_news" and getattr(data, "cards", None):
        enriched_cards = await enrich_news_card_thumbnails(list(data.cards))
        if enriched_cards != list(data.cards):
            data = data.model_copy(update={"cards": enriched_cards})
    elif section.block_kind == "people" and getattr(data, "cards", None):
        targets = [(i, c) for i, c in enumerate(data.cards) if c.image_url is None]
        if targets:
            resolved = await asyncio.gather(
                *(_resolve_person_image(c.name) for _, c in targets),
                return_exceptions=True,
            )
            new_cards = list(data.cards)
            for (idx, card), info in zip(targets, resolved, strict=True):
                if isinstance(info, Exception) or info is None:
                    continue
                update = {
                    "image_url": info.image_url,
                    "image_source": info.image_source,
                }
                if card.profile_url is None and info.profile_url:
                    update["profile_url"] = info.profile_url
                try:
                    new_cards[idx] = type(card).model_validate(
                        {**card.model_dump(), **update}
                    )
                except Exception as exc:
                    logger.debug(
                        "people: invalid image_url for %s (%s)", card.name, exc
                    )
            if new_cards != list(data.cards):
                data = data.model_copy(update={"cards": new_cards})

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
        r.section_event(
            section.section_id,
            "extract_dropped",
            reason="citation_integrity",
            unknown=sorted(unknown),
        )
        return None

    if not spec.is_minimum_viable(data):
        logger.info(
            "block_extract dropped %s: is_minimum_viable=False", section.section_id
        )
        r.section_event(section.section_id, "extract_dropped", reason="below_threshold")
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

    r.section_event(section.section_id, "extract_ok", citations=len(citations))
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
    entities: list[str] | None = None,
    reporter: PipelineReporter | None = None,
    notes: EditorNotes | None = None,
) -> list[RenderedSection]:
    """Extract all sections in parallel. Dropped sections are filtered out."""
    coros = [
        extract_one_section(
            section=s,
            sources=evidence_by_section.get(s.section_id, []),
            canonical_title=canonical_title,
            entities=entities,
            reporter=reporter,
            editor_note=merge_note(s.section_id, notes),
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
