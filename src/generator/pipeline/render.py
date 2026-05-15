"""Stage 7 — Render. EventPage → editorial two-column HTML.

The page is structured as:
  chrome (hero)  →  horizontal sticky nav  →  N need sections (main column)
                                          ↘  reference sidebar (right column)

Each need section emits a typed-block sequence: paragraph / timeline / chart
/ newsfeed / factsheet / map / reactions. Modules adapt themselves to one of
these shapes via `blocks.module_to_block()`.
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
    EventFacts,
    EventLayout,
    EventMeta,
    EventPage,
    EventSubject,
    NeedCurationPlan,
    NeedId,
    RenderedSection,
    Source,
    TypedModule,
    WikipediaCardData,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_TEMPLATES_DIR = _PROJECT_ROOT / "templates"

_CHROME_KINDS = {"hero"}
_MAX_MILESTONES = 6


def slugify(text: str) -> str:
    """Slug for a one-sentence input. Truncates to keep filenames short."""
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    parts = base.split("-")[:4]
    return "-".join(parts) or "event"


def build_page(
    input_sentence: str,
    page_id: str,
    subject: EventSubject,
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
        subject=subject,
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
        modules=[],  # editorial path: no modules
        layout=layout,
        sources=sources,
        needs_coverage={},
        uncovered_needs=[],
        need_plans=[],
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


def _build_sections(
    page: EventPage, *, consumed_by_chrome: set[str] | None = None
) -> list[dict]:
    """Assemble the ordered list of need sections for the template.

    ``consumed_by_chrome`` lists module kinds that have already been rendered
    by page chrome (e.g. the schedule module when its milestones are shown in
    the right reference sidebar) so they don't get re-emitted as orphan blocks.
    """
    modules_by_kind = {m.kind: m for m in page.modules}
    extra_consumed = consumed_by_chrome or set()
    rendered: set[str] = (set(_CHROME_KINDS) | extra_consumed) & set(
        modules_by_kind.keys()
    )
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
            section_blocks.append(module_to_block(mod, page.sources, override=override))
            rendered.add(kind)
        if section_blocks:
            sections.append(
                {
                    "need_id": plan.need_id,
                    "section_id": plan.need_id,
                    "title": plan.section_title,
                    "rationale": plan.rationale,
                    "category": plan.category,
                    "opinion_subtag": plan.opinion_subtag,
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
                "section_id": "more",
                "title": "More on this topic",
                "rationale": "",
                "category": None,
                "opinion_subtag": None,
                "blocks": [module_to_block(m, page.sources) for m in orphan_modules],
            }
        )

    return sections


def _build_milestones(page: EventPage) -> list[dict]:
    """Build the right-rail milestone timeline entries from the schedule module.

    Returns at most ``_MAX_MILESTONES`` items, sorted chronologically. Each
    item is a dict with ``day``, ``time``, ``label``, ``location``, ``state``
    where state is one of ``past``/``future``/``current``. The
    chronologically-last future entry is promoted to ``current`` (the next-up
    milestone). Items whose ``time_iso`` cannot be parsed are silently dropped.
    Returns ``[]`` when no schedule module exists or no items are flagged
    ``is_milestone``.
    """
    sched = next((m for m in page.modules if m.kind == "schedule"), None)
    if sched is None:
        return []
    now = datetime.now(timezone.utc)

    # Parse timestamps first; drop items that cannot be parsed.
    parsed: list[tuple[datetime, object]] = []
    for i in [item for item in sched.data.items if item.is_milestone]:
        try:
            ts = datetime.fromisoformat(i.time_iso.replace("Z", "+00:00"))
        except ValueError:
            continue
        parsed.append((ts, i))

    # Sort by parsed datetime, then cap.
    parsed.sort(key=lambda pair: pair[0])
    parsed = parsed[:_MAX_MILESTONES]

    out: list[dict] = []
    for ts, i in parsed:
        ts_utc = ts.astimezone(timezone.utc)
        state = "past" if ts_utc < now else "future"
        out.append(
            {
                "day": ts_utc.strftime("%b %d"),
                "time": ts_utc.strftime("%H:%M UTC"),
                "label": i.label,
                "location": i.location,
                "state": state,
            }
        )
    if out and out[-1]["state"] == "future":
        out[-1]["state"] = "current"
    return out


def render_html(page: EventPage) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )

    palette_block = palette_css_vars(_select_palette_id(page))
    stylesheet = (_TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8")
    toc_js = (_TEMPLATES_DIR / "toc.js").read_text(encoding="utf-8")

    hero_module = next((m for m in page.modules if m.kind == "hero"), None)

    source_index = {s.id: i + 1 for i, s in enumerate(page.sources)}
    milestones = _build_milestones(page)
    # When the schedule module has driven the right-rail milestone timeline,
    # don't also re-emit it as an inline orphan block in the main flow.
    consumed_by_chrome = {"schedule"} if milestones else set()
    if page.editorial_sections is not None:
        sections = _build_editorial_section_dicts(page.editorial_sections)
    else:
        sections = _build_sections(page, consumed_by_chrome=consumed_by_chrome)

    template = env.get_template("layout.html")
    return template.render(
        page=page,
        hero_module=hero_module,
        sections=sections,
        source_index=source_index,
        palette_css_block=palette_block,
        stylesheet=stylesheet,
        toc_js=toc_js,
        jsonld=_build_jsonld(page),
        milestones=milestones,
    )
