"""Four named aesthetic presets — complete LayoutConfig instances.

`reference` is the fallback for unknown archetypes.
"""

from __future__ import annotations

from generator.schema import (
    AestheticPresetId,
    AuxLayout,
    ColumnsLayout,
    ContainerPadding,
    DesignTokens,
    HeroLayout,
    LayoutConfig,
    LayoutSignals,
    MobileLayout,
)

# Allowed in aux slot. Schema forbids media_coverage / schedule / reactions.
_AUX_WHITELIST = ["infobox", "kpi_numbers", "where_to_watch"]


def _container() -> ContainerPadding:
    return ContainerPadding(desktop=24, mobile=16)


def _mobile() -> MobileLayout:
    return MobileLayout(
        breakpoint_px=768,
        aux_strategy="inline_after_hero",
        aux_priority_in_mobile=["infobox", "where_to_watch"],
    )


PRESETS: dict[AestheticPresetId, LayoutConfig] = {
    "live_dominance": LayoutConfig(
        container_max_width=1180,
        container_padding=_container(),
        hero=HeroLayout(placement="full_bleed", height_px=420, mobile_height_px=260),
        columns=ColumnsLayout(count=2, ratios=[0.75, 0.25], gap_px=32),
        aux=AuxLayout(
            sticky_first_item=True,
            max_items=3,
            max_height_pct_of_main=0.8,
            whitelist=_AUX_WHITELIST,
        ),
        mobile=_mobile(),
        design_tokens=DesignTokens(
            palette="festive_warm", density="standard", typography_scale="standard"
        ),
        signals=LayoutSignals(live_pill=True, sticky_top_strip="live"),
    ),
    "product_focus": LayoutConfig(
        container_max_width=1180,
        container_padding=_container(),
        hero=HeroLayout(placement="in_main", height_px=360, mobile_height_px=220),
        columns=ColumnsLayout(count=2, ratios=[0.60, 0.40], gap_px=40),
        aux=AuxLayout(
            sticky_first_item=True,
            max_items=4,
            max_height_pct_of_main=1.0,
            whitelist=_AUX_WHITELIST,
        ),
        mobile=_mobile(),
        design_tokens=DesignTokens(
            palette="minimal_tech", density="sparse", typography_scale="loose"
        ),
        signals=LayoutSignals(live_pill=False, sticky_top_strip=None),
    ),
    "imminent_event": LayoutConfig(
        container_max_width=1180,
        container_padding=_container(),
        hero=HeroLayout(placement="full_bleed", height_px=440, mobile_height_px=300),
        columns=ColumnsLayout(count=2, ratios=[0.65, 0.35], gap_px=32),
        aux=AuxLayout(
            sticky_first_item=True,
            max_items=3,
            max_height_pct_of_main=0.9,
            whitelist=_AUX_WHITELIST,
        ),
        mobile=_mobile(),
        design_tokens=DesignTokens(
            palette="bold_sport", density="standard", typography_scale="standard"
        ),
        signals=LayoutSignals(live_pill=False, sticky_top_strip=None),
    ),
    "reference": LayoutConfig(
        container_max_width=1180,
        container_padding=_container(),
        hero=HeroLayout(placement="in_main", height_px=320, mobile_height_px=200),
        columns=ColumnsLayout(count=2, ratios=[0.65, 0.35], gap_px=32),
        aux=AuxLayout(
            sticky_first_item=False,
            max_items=3,
            max_height_pct_of_main=1.0,
            whitelist=_AUX_WHITELIST,
        ),
        mobile=_mobile(),
        design_tokens=DesignTokens(
            palette="neutral_news", density="standard", typography_scale="standard"
        ),
        signals=LayoutSignals(live_pill=False, sticky_top_strip=None),
    ),
}


def get_preset(preset_id: str) -> LayoutConfig:
    """Return the preset, falling back to `reference` for unknown ids."""
    return PRESETS.get(preset_id, PRESETS["reference"])
