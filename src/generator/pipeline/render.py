"""Stage 7 — Render. Composes the EventPage and renders placeholder HTML."""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

from jinja2 import Environment, FileSystemLoader, select_autoescape

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

_TEMPLATES_DIR = Path(__file__).resolve().parents[3] / "templates"


def slugify(text: str) -> str:
    """Slug for a one-sentence input. Truncates to keep filenames short."""
    base = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    parts = base.split("-")[:4]
    return "-".join(parts) or "event"


def _compute_needs_coverage(modules: list[TypedModule]) -> dict[NeedId, list[str]]:
    coverage: dict[NeedId, list[str]] = defaultdict(list)
    for m in modules:
        for need in m.serves_needs:
            coverage[need].append(m.module_id)
    # ensure every NeedId key is present
    for need in get_args(NeedId):
        coverage.setdefault(need, [])
    return dict(coverage)


def build_page(
    input_sentence: str,
    page_id: str,
    triage: TriageOutput,
    aesthetic: AestheticPlanOutput,
    sources: list[Source],
    modules: list[TypedModule],
    trace_id: str,
) -> EventPage:
    now = datetime.now(timezone.utc).isoformat()
    coverage = _compute_needs_coverage(modules)
    uncovered: list[NeedId] = [n for n, ids in coverage.items() if not ids]  # type: ignore[misc]
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
        needs_coverage=coverage,
        uncovered_needs=uncovered,
        meta=EventMeta(
            last_updated=now,
            editor_approved=True,
            editor_id="cli_user@local",
            pipeline_trace_id=trace_id,
        ),
    )


def render_html(page: EventPage) -> str:
    env = Environment(
        loader=FileSystemLoader(str(_TEMPLATES_DIR)),
        autoescape=select_autoescape(["html"]),
    )
    template = env.get_template("placeholder.html")
    return template.render(page=page)
