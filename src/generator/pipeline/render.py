"""Stage 7 — Render. EventPage → editorial two-column HTML.

The page is structured as:
  chrome (hero)  →  horizontal sticky nav  →  N need sections (main column)
                                          ↘  reference sidebar (right column)

Each need section emits a typed-block sequence: paragraph / timeline / chart
/ newsfeed / factsheet / map / reactions. Sections are RenderedSection objects
produced by the block_extract stage.
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
            }
        )
    return out


def subject_from_facts(facts: EventFacts, canonical_title: str) -> EventSubject:
    return EventSubject(
        title=canonical_title,
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
    sections = _build_editorial_section_dicts(page.editorial_sections)

    template = env.get_template("layout.html")
    return template.render(
        page=page,
        hero_module=None,
        sections=sections,
        source_index=source_index,
        palette_css_block=palette_block,
        stylesheet=stylesheet,
        toc_js=toc_js,
        jsonld=_build_jsonld(page),
        milestones=[],
    )
