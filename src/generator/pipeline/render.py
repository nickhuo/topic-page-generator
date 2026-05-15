"""Stage 7 — Render. EventPage → editorial two-column HTML.

The page is structured as:
  chrome (hero)  →  horizontal sticky nav  →  N need sections (main column)
                                          ↘  reference sidebar (right column)

Each need section emits a typed-block sequence: paragraph / chart / newsfeed
/ reactions / gallery in the main column; timeline blocks render exclusively
in the right sidebar via blocks/timeline_sidebar.html. Sections are
RenderedSection objects produced by the block_extract stage.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from generator.layout.tokens import palette_css_vars
from generator.schema import (
    EventFacts,
    EventLayout,
    EventMeta,
    EventPage,
    EventSubject,
    HeroImage,
    RenderedSection,
    Source,
    WikipediaCardData,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"


def slugify(text: str) -> str:
    """Slug for a one-sentence input. Truncates to keep filenames short."""
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    parts = base.split("-")[:4]
    return "-".join(parts) or "event"


def build_editorial_page(
    *,
    input_sentence: str,
    page_id: str,
    subject: EventSubject,
    layout: EventLayout,
    sources: list[Source],
    editorial_sections: list[RenderedSection],
    trace_id: str,
    meta: EventMeta,
    wikipedia_card: WikipediaCardData | None = None,
    hero_image: HeroImage | None = None,
) -> EventPage:
    """Construct an EventPage that uses the editorial render path."""
    return EventPage(
        page_id=page_id,
        input_sentence=input_sentence,
        generated_at=datetime.now(timezone.utc).isoformat(),
        subject=subject,
        layout=layout,
        sources=sources,
        wikipedia_card=wikipedia_card,
        hero_image=hero_image,
        editorial_sections=editorial_sections,
        meta=meta,
    )


def _build_editorial_section_dicts(
    editorial: list[RenderedSection],
) -> list[dict]:
    """Mirror _build_sections() shape for use with templates/needs/section.html."""
    out = []
    for idx, rs in enumerate(editorial, start=1):
        out.append(
            {
                "need_id": rs.section_id,
                "section_id": rs.section_id,
                "title": rs.section_id.replace("_", " ").title(),
                "category": None,  # no fact/opinion chip in editorial path
                "blocks": [rs.block_data],
                "section_index": idx,
                "placement": rs.placement,
            }
        )
    return out


def _partition_by_placement(
    section_dicts: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Split rendered sections into (main_column, sidebar_column)."""
    main: list[dict] = []
    sidebar: list[dict] = []
    for s in section_dicts:
        (sidebar if s.get("placement") == "sidebar" else main).append(s)
    # Re-index main sections so the chip nav and screen-label numbering stay
    # contiguous after sidebar sections are pulled out.
    for new_idx, s in enumerate(main, start=1):
        s["section_index"] = new_idx
    return main, sidebar


def subject_from_facts(facts: EventFacts, canonical_title: str) -> EventSubject:
    # Subtitle is grounded by the ground stage; fall back to `what` if the
    # model didn't fill it (e.g. older fixtures) — never invent.
    subtitle = (facts.subtitle or facts.what)[:240]
    return EventSubject(
        title=canonical_title,
        subtitle=subtitle,
        entities=facts.entities,
        when=facts.when,
        where=facts.where,
    )


def _build_jsonld(page: EventPage) -> str:
    schema_type = "Event" if page.subject.when else "NewsArticle"
    data: dict = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": page.subject.title,
        "description": page.input_sentence,
    }
    if page.subject.when:
        data["startDate"] = page.subject.when
    else:
        data["datePublished"] = page.meta.last_updated
    if page.subject.where:
        data["location"] = page.subject.where
    return json.dumps(data, separators=(",", ":"))


def _select_palette_id(page: EventPage) -> str:
    """Resolve the palette id to inject as CSS vars.

    Aesthetic overrides win when present; otherwise infer from preset.
    """
    # Aesthetic overrides aren't stored on the page directly; preset is.
    preset = page.layout.preset_id
    return {
        "live_dominance": "urgent_light",
        "product_focus": "minimal_tech",
        "imminent_event": "bold_sport",
        "reference": "neutral_news",
    }.get(preset, "neutral_news")


def render_html(page: EventPage) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    palette_block = palette_css_vars(_select_palette_id(page))
    stylesheet = (_TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8")
    toc_js = (_TEMPLATES_DIR / "toc.js").read_text(encoding="utf-8")

    source_index = {s.id: i + 1 for i, s in enumerate(page.sources)}
    source_by_id = {s.id: s for s in page.sources}
    all_sections = _build_editorial_section_dicts(page.editorial_sections)
    main_sections, sidebar_sections = _partition_by_placement(all_sections)
    hero = _build_hero_context(page)

    # Jinja helper: turn a list of source_ids into a cite-cluster context dict
    # (stacked favicons + popover mini-newsfeed). Templates call this per
    # paragraph / per entry rather than rendering raw `[N]` markers.
    env.globals["cite_cluster"] = lambda source_ids: _build_cite_cluster(
        source_ids or [], source_by_id, source_index
    )

    template = env.get_template("layout.html")
    return template.render(
        page=page,
        hero=hero,
        sections=main_sections,
        sidebar_sections=sidebar_sections,
        source_index=source_index,
        palette_css_block=palette_block,
        stylesheet=stylesheet,
        toc_js=toc_js,
        jsonld=_build_jsonld(page),
        milestones=[],
    )


# --- Cite cluster (stacked publisher favicons + hover popover) ----------------
_MAX_STACKED_LOGOS = 3
_S2_FAVICON = "https://www.google.com/s2/favicons?domain={host}&sz=64"


def _favicon_for(source) -> str:
    host = ""
    url = str(getattr(source, "url", "") or "")
    if "://" in url:
        host = url.split("://", 1)[1].split("/", 1)[0]
    return _S2_FAVICON.format(host=host or "example.com")


def _build_cite_cluster(
    source_ids: list[str],
    source_by_id: dict[str, "Source"],
    source_index: dict[str, int],
) -> dict | None:
    """Build a cite-cluster context: stacked logos + popover cards.

    Returns None when there are no resolvable sources — templates use
    `{% set cluster = cite_cluster([...]) %}{% if cluster %}…` to skip.
    De-duplicates `source_ids` while preserving order.
    """
    seen: set[str] = set()
    resolved = []
    for sid in source_ids:
        if sid in seen or sid not in source_by_id:
            continue
        seen.add(sid)
        resolved.append(source_by_id[sid])
    if not resolved:
        return None

    logos = [
        {
            "favicon_url": _favicon_for(s),
            "publisher": s.publisher.name,
        }
        for s in resolved[:_MAX_STACKED_LOGOS]
    ]
    cards = [
        {
            "source_id": s.id,
            "url": str(s.url),
            "title": s.title,
            "publisher": s.publisher.name,
            "favicon_url": _favicon_for(s),
            "summary": (s.summary or "")[:240],
            "thumbnail_url": str(s.thumbnail_url) if s.thumbnail_url else None,
            "ref_number": source_index.get(s.id),
        }
        for s in resolved
    ]
    extra = max(0, len(resolved) - _MAX_STACKED_LOGOS)
    return {
        "logos": logos,
        "total": len(resolved),
        "extra": extra,
        "cards": cards,
    }


def _build_hero_context(page: EventPage) -> dict:
    """Hero data for the page chrome.

    Subtitle comes from `subject.subtitle` (produced by the ground stage).
    Hero image prefers `page.hero_image`; falls back to the first gallery
    section's first image.
    """
    image_url, image_alt = _hero_image(page)
    dateline = _hero_dateline(page.subject)
    return {
        "title": page.subject.title,
        "subtitle": page.subject.subtitle,
        "image_url": image_url,
        "image_alt": image_alt,
        "dateline": dateline,
        "entities": page.subject.entities,
    }


def _hero_image(page: EventPage) -> tuple[str | None, str | None]:
    """Page's hero image: prefer the dedicated hero_image, fall back to gallery."""
    if page.hero_image is not None:
        return str(page.hero_image.image_url), page.hero_image.alt_text
    for rs in page.editorial_sections:
        if rs.block_kind == "gallery":
            items = getattr(rs.block_data, "items", None) or []
            if items:
                first = items[0]
                return str(first.image_url), first.alt_text or first.caption
    return None, None


def _hero_dateline(subject: EventSubject) -> str | None:
    """A short `when · where` line for the hero meta row."""
    when = (subject.when or "")[:10] if subject.when else None
    where = subject.where
    parts = [p for p in (when, where) if p]
    return " · ".join(parts) if parts else None
