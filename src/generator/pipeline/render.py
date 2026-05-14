"""Stage 7 — Render. EventPage → editorial single-column HTML.

The page is structured as:
  chrome (hero + countdown)  →  needs nav  →  N need sections  →  footer

Each need section emits a typed-block sequence: paragraph / timeline / chart
/ newsfeed / factsheet / map. Modules adapt themselves to one of these
shapes via `blocks.module_to_block()`.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from generator.blocks import module_to_block
from generator.layout.tokens import palette_css_vars
from generator.schema import (
    AestheticPlanOutput,
    EventLayout,
    EventMeta,
    EventPage,
    EventSubject,
    NeedCurationPlan,
    NeedId,
    Source,
    TriageOutput,
    TypedModule,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"

_CHROME_KINDS = {"hero", "countdown"}


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
    need_plans: list[NeedCurationPlan] | None = None,
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
        need_plans=need_plans or [],
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


def _select_palette_id(page: EventPage) -> str:
    """Resolve the palette id to inject as CSS vars.

    Aesthetic overrides win when present; otherwise infer from preset.
    """
    # Aesthetic overrides aren't stored on the page directly; preset is.
    preset = page.layout.preset_id
    return {
        "live_dominance": "urgent_red",
        "product_focus": "minimal_tech",
        "imminent_event": "bold_sport",
        "reference": "neutral_news",
    }.get(preset, "neutral_news")


def _build_sections(page: EventPage) -> list[dict]:
    """Assemble the ordered list of need sections for the template."""
    modules_by_kind = {m.kind: m for m in page.modules}
    rendered: set[str] = set(_CHROME_KINDS) & set(modules_by_kind.keys())
    sections: list[dict] = []

    activated = sorted(
        (p for p in page.need_plans if p.activated), key=lambda p: p.rank
    )
    for plan in activated:
        section_blocks = []
        for kind in plan.assigned_modules:
            if kind in rendered:
                continue
            mod = modules_by_kind.get(kind)
            if mod is None:
                continue
            override = plan.render_overrides.get(kind)
            section_blocks.append(
                module_to_block(mod, page.sources, override=override)
            )
            rendered.add(kind)
        if section_blocks:
            sections.append(
                {
                    "need_id": plan.need_id,
                    "title": plan.section_title,
                    "rationale": plan.rationale,
                    "blocks": section_blocks,
                }
            )

    # Orphans: modules that weren't assigned to any activated need.
    orphan_modules = [
        m
        for m in page.modules
        if m.kind not in rendered and m.kind not in _CHROME_KINDS
    ]
    if orphan_modules:
        sections.append(
            {
                "need_id": "more",
                "title": "More on this topic",
                "rationale": "",
                "blocks": [
                    module_to_block(m, page.sources) for m in orphan_modules
                ],
            }
        )

    return sections


def render_html(page: EventPage) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    palette_block = palette_css_vars(_select_palette_id(page))
    stylesheet = (_TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8")

    hero_module = next(
        (m for m in page.modules if m.kind == "hero"), None
    )
    countdown_module = next(
        (m for m in page.modules if m.kind == "countdown"), None
    )

    source_index = {s.id: i + 1 for i, s in enumerate(page.sources)}
    sections = _build_sections(page)

    template = env.get_template("layout.html")
    return template.render(
        page=page,
        hero_module=hero_module,
        countdown_module=countdown_module,
        sections=sections,
        source_index=source_index,
        palette_css_block=palette_block,
        stylesheet=stylesheet,
        jsonld=_build_jsonld(page),
    )
