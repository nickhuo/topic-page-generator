from generator.pipeline.archetype_table import lookup, ARCHETYPES


def test_all_four_known_archetypes_present():
    for k in ("product_launch", "live_cultural_event", "scheduled_sports_event", "generic_event"):
        assert k in ARCHETYPES
        assert ARCHETYPES[k].composition  # non-empty


def test_unknown_falls_through_to_generic():
    unknown = lookup("not_a_real_type")
    generic = lookup("generic_event")
    assert unknown == generic


def test_product_launch_includes_hero_and_infobox():
    plan = lookup("product_launch")
    kinds = [c.module_kind for c in plan.composition]
    assert "hero" in kinds
    assert "infobox" in kinds
    assert plan.layout_preset_id == "product_focus"


def test_live_cultural_uses_live_dominance():
    assert lookup("live_cultural_event").layout_preset_id == "live_dominance"


def test_scheduled_sports_uses_imminent_event():
    assert lookup("scheduled_sports_event").layout_preset_id == "imminent_event"
