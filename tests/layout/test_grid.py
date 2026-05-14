import pytest

from generator.layout.grid import (
    ARTIFACT_PARTIAL,
    ResolvedLayout,
    compose,
)
from tests.fixtures import (
    background_module,
    event_page,
    hero_module,
    infobox_module,
    media_coverage_module,
    source,
)


def test_compose_returns_resolved_layout():
    page = event_page(modules=[hero_module(), infobox_module()])
    rl = compose(page)
    assert isinstance(rl, ResolvedLayout)
    assert rl.config.design_tokens.palette  # palette resolved


def test_source_index_is_one_based():
    page = event_page(modules=[hero_module()])
    rl = compose(page)
    assert rl.source_index["s1"] == 1
    assert rl.source_index["s2"] == 2


def test_aux_whitelist_demotes_forbidden_kinds():
    # media_coverage forced into aside should be demoted to primary
    page = event_page(modules=[hero_module(), media_coverage_module(slot="aside")])
    rl = compose(page)
    aux_kinds = [m.kind for m in rl.slots["aside"]]
    primary_kinds = [m.kind for m in rl.slots["primary"]]
    assert "media_coverage" not in aux_kinds
    assert "media_coverage" in primary_kinds


def test_should_render_false_drops_module():
    page = event_page(modules=[hero_module(), background_module(empty=True)])
    rl = compose(page)
    all_modules = [m for ms in rl.slots.values() for m in ms]
    assert all(m.kind != "background" for m in all_modules), (
        "Empty background should have been dropped by should_render gate"
    )


def test_unknown_preset_falls_back_to_reference():
    page = event_page(modules=[hero_module()], preset_id="totally_unknown")  # type: ignore[arg-type]
    rl = compose(page)
    assert rl.config.design_tokens.palette == "neutral_news"


def test_aux_overflow_moves_to_primary_tail():
    # reference preset has aux.max_items=3. Force 5 infoboxes into aside.
    boxes = [
        infobox_module().model_copy(update={"module_id": f"m{i}"}) for i in range(5)
    ]
    page = event_page(modules=[hero_module(), *boxes])
    rl = compose(page)
    assert len(rl.slots["aside"]) == 3
    assert sum(1 for m in rl.slots["primary"] if m.kind == "infobox") == 2


def test_artifact_partial_map_covers_eleven_kinds():
    expected = {
        "hero", "infobox", "schedule", "countdown", "comparison",
        "changelog", "reactions", "official_statements", "media_coverage",
        "where_to_watch", "background",
    }
    # kpi_numbers handled inline in layout.html, not via partial map
    assert expected <= set(ARTIFACT_PARTIAL.keys())
