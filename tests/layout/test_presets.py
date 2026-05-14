import pytest

from generator.layout.presets import PRESETS, get_preset
from generator.schema import LayoutConfig


def test_all_four_presets_present():
    assert set(PRESETS.keys()) == {
        "live_dominance", "product_focus", "imminent_event", "reference",
    }


def test_presets_are_layoutconfig_instances():
    for cfg in PRESETS.values():
        assert isinstance(cfg, LayoutConfig)


def test_live_dominance_signals_live_pill():
    assert PRESETS["live_dominance"].signals.live_pill is True


def test_imminent_event_countdown_in_hero():
    assert PRESETS["imminent_event"].signals.countdown_in_hero is True


def test_product_focus_uses_minimal_tech_palette():
    assert PRESETS["product_focus"].design_tokens.palette == "minimal_tech"
    assert PRESETS["product_focus"].design_tokens.density == "sparse"


def test_reference_is_fallback_for_unknown_archetypes():
    assert get_preset("totally_unknown_preset_id").design_tokens.palette == "neutral_news"


@pytest.mark.parametrize("pid,ratios", [
    ("live_dominance", [0.75, 0.25]),
    ("product_focus", [0.60, 0.40]),
    ("imminent_event", [0.65, 0.35]),
    ("reference", [0.65, 0.35]),
])
def test_column_ratios(pid, ratios):
    assert PRESETS[pid].columns.ratios == ratios


def test_aux_whitelist_excludes_forbidden_kinds():
    forbidden = {"media_coverage", "schedule", "reactions"}
    for pid, cfg in PRESETS.items():
        assert not (set(cfg.aux.whitelist) & forbidden), (
            f"{pid} aux whitelist contains forbidden kind"
        )
