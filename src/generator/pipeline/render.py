"""Stage 7 — Render. Composes EventPage → ResolvedLayout → HTML."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

from generator.layout.grid import ARTIFACT_PARTIAL, QUOTE_DENSITY, ResolvedLayout, compose
from generator.layout.tokens import palette_css_vars
from generator.schema import (
    AestheticPlanOutput,
    EventLayout,
    EventMeta,
    EventPage,
    EventSubject,
    NeedId,
    Source,
    TriageOutput,
    TypedModule,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"


def slugify(text: str) -> str:
    """Slug for a one-sentence input. Truncates to keep filenames short."""
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    parts = base.split("-")[:4]
    return "-".join(parts) or "event"


def build_page(
    input_sentence: str,
    page_id: str,
    triage: TriageOutput,
    aesthetic: AestheticPlanOutput,
    sources: list[Source],
    modules: list[TypedModule],
    trace_id: str,
    *,
    needs_coverage: dict[NeedId, list[str]],
    uncovered_needs: list[NeedId],
) -> EventPage:
    now = datetime.now(timezone.utc).isoformat()
    return EventPage(
        page_id=page_id,
        input_sentence=input_sentence,
        generated_at=now,
        subject=EventSubject(
            primary_entity=triage.primary_entity or "Unknown",
            event_type_hint=triage.event_type_hint or "generic",
            temporal_posture=triage.temporal_posture or "recent",
            time_anchor=triage.time_anchor,
        ),
        modules=modules,
        layout=EventLayout(preset_id=aesthetic.preset_id, overrides=None),
        sources=sources,
        needs_coverage=needs_coverage,
        uncovered_needs=uncovered_needs,
        meta=EventMeta(
            last_updated=now,
            editor_approved=True,
            editor_id="cli_user@local",
            pipeline_trace_id=trace_id,
        ),
    )


def _build_jsonld(page: EventPage) -> str:
    schema_type = "Event" if page.subject.time_anchor else "NewsArticle"
    data: dict = {
        "@context": "https://schema.org",
        "@type": schema_type,
        "name": page.subject.primary_entity,
        "description": page.input_sentence,
    }
    if page.subject.time_anchor:
        data["startDate"] = page.subject.time_anchor
    else:
        data["datePublished"] = page.meta.last_updated
    return json.dumps(data, separators=(",", ":"))


def _make_cite(source_index: dict[str, int]):
    def cite(source_id: str) -> Markup:
        n = source_index.get(source_id)
        if n is None:
            return Markup("")
        return Markup(
            f'<sup class="cite-num"><a href="#src-{n}">[{n}]</a></sup>'
        )
    return cite


def render_html(page: EventPage) -> str:
    layout: ResolvedLayout = compose(page)

    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    stylesheet = (_TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8")
    palette_block = palette_css_vars(layout.config.design_tokens.palette)

    template = env.get_template("layout.html")
    return template.render(
        page=page,
        layout=layout,
        artifact_partial=ARTIFACT_PARTIAL,
        quote_density=QUOTE_DENSITY,
        cite=_make_cite(layout.source_index),
        palette_css_block=palette_block,
        stylesheet=stylesheet,
        jsonld=_build_jsonld(page),
    )
