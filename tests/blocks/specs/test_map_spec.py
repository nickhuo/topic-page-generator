from generator.blocks.schema import Location, MapBlockData
from generator.blocks.specs.map import MapBlockSpec


def test_map_spec_metadata():
    spec = MapBlockSpec()
    assert spec.kind == "map"
    assert spec.template_path == "blocks/map.html"


def test_map_minimum_viable_needs_location_with_coords():
    spec = MapBlockSpec()
    no_coords = MapBlockData(locations=[Location(name="Somewhere")])
    with_coords = MapBlockData(
        locations=[Location(name="Paris", lat=48.85, lon=2.35)]
    )
    assert spec.is_minimum_viable(no_coords) is False
    assert spec.is_minimum_viable(with_coords) is True
