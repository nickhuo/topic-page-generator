"""Tests for the hero module: schema binding, render gate, registry."""

import importlib

from generator.modules import MODULE_REGISTRY
from generator.schema import HeroData


def _get_hero_module():
    """Return the live HeroModule class, re-registering if test_base clobbered it."""
    import generator.modules.hero as _hero_mod

    importlib.reload(_hero_mod)
    return _hero_mod.HeroModule


def test_hero_registered():
    # Reload triggers __init_subclass__ re-registration; necessary because
    # test_base creates a _Hero stub with kind="hero" then pops it in finally.
    HeroModule = _get_hero_module()
    assert MODULE_REGISTRY["hero"] is HeroModule


def test_hero_metadata():
    import generator.modules.hero as _hero_mod

    HeroModule = _hero_mod.HeroModule
    assert HeroModule.kind == "hero"
    assert HeroModule.serves_needs == ["what_happened"]
    assert "HeroBanner" in HeroModule.allowed_artifacts
    assert HeroModule.data_schema is HeroData
    assert isinstance(HeroModule.extraction_prompt_template, str)
    assert "{title}" in HeroModule.extraction_prompt_template
    assert "{evidence_block}" in HeroModule.extraction_prompt_template


def test_hero_should_render():
    import generator.modules.hero as _hero_mod

    HeroModule = _hero_mod.HeroModule
    valid = HeroData(title="t", summary="s", image_alt="alt")
    assert HeroModule().should_render(valid)
    empty = HeroData(title="", summary="", image_alt="")
    assert not HeroModule().should_render(empty)


def test_hero_should_render_none():
    import generator.modules.hero as _hero_mod

    HeroModule = _hero_mod.HeroModule
    assert not HeroModule().should_render(None)
