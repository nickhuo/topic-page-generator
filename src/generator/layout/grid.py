"""Layout composition: merge preset + overrides, route modules to slots."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from generator.layout.presets import get_preset
from generator.layout.tokens import PALETTES
from generator.modules import MODULE_REGISTRY, all_modules
from generator.schema import (
    EventPage,
    LayoutConfig,
    Slot,
    SourceId,
    TypedModule,
)

# Module kind → partial filename under templates/artifacts/.
# `kpi_numbers` is intentionally omitted; it's inlined in layout.html.
ARTIFACT_PARTIAL: dict[str, str] = {
    "hero": "hero.html",
    "infobox": "infobox.html",
    "schedule": "timeline.html",
    "countdown": "countdown.html",
    "comparison": "comparison_table.html",
    "changelog": "changelog_list.html",
    "reactions": "quote.html",
    "official_statements": "quote.html",
    "media_coverage": "coverage_breakdown.html",
    "where_to_watch": "where_to_watch.html",
    "background": "explainer.html",
}

# Density param consumed by quote.html.
QUOTE_DENSITY: dict[str, str] = {
    "reactions": "ribbon",
    "official_statements": "card",
}


class ResolvedLayout(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    config: LayoutConfig
    slots: dict[Slot, list[TypedModule]]
    palette_vars: dict[str, str]
    source_index: dict[SourceId, int]


def _empty_slots() -> dict[Slot, list[TypedModule]]:
    return {"hero": [], "primary": [], "aside": [], "tail": [], "footer": []}


def _should_render(module: TypedModule) -> bool:
    """Use the module class's render gate; if not registered, render by default."""
    cls = MODULE_REGISTRY.get(module.kind)
    if cls is None:
        return True
    try:
        return cls().should_render(module.data)
    except Exception:
        return True


def compose(event_page: EventPage) -> ResolvedLayout:
    # Ensure MODULE_REGISTRY is populated.
    all_modules()

    base = get_preset(event_page.layout.preset_id)
    config = event_page.layout.overrides or base

    slots = _empty_slots()
    whitelist = set(config.aux.whitelist)

    for module in event_page.modules:
        if not _should_render(module):
            continue
        slot: Slot = module.slot
        if slot == "aside" and module.kind not in whitelist:
            slot = "primary"
        slots[slot].append(module)

    if len(slots["aside"]) > config.aux.max_items:
        overflow = slots["aside"][config.aux.max_items:]
        slots["aside"] = slots["aside"][: config.aux.max_items]
        slots["primary"].extend(overflow)

    source_index = {s.id: i for i, s in enumerate(event_page.sources, start=1)}
    palette_vars = dict(PALETTES[config.design_tokens.palette])

    return ResolvedLayout(
        config=config,
        slots=slots,
        palette_vars=palette_vars,
        source_index=source_index,
    )
