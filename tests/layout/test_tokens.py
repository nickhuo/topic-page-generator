from generator.layout.tokens import PALETTES, palette_css_vars, REQUIRED_VARS


def test_all_six_palettes_present():
    assert set(PALETTES.keys()) == {
        "festive_warm", "minimal_tech", "urgent_red",
        "muted_solemn", "bold_sport", "neutral_news",
    }


def test_every_palette_defines_required_vars():
    for pid, vars_ in PALETTES.items():
        missing = REQUIRED_VARS - set(vars_.keys())
        assert not missing, f"{pid} missing {missing}"


def test_palette_css_vars_returns_inline_block():
    css = palette_css_vars("minimal_tech")
    assert css.startswith(":root")
    assert "--color-bg" in css
    assert "--color-accent" in css
