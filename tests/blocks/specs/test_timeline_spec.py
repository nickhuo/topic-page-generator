from generator.blocks.schema import TimelineBlockData, TimelineEntry
from generator.blocks.specs.timeline import TimelineBlockSpec


def _entry(title="t", phase="past") -> TimelineEntry:
    return TimelineEntry(title=title, time="2026-05-15", temporal_phase=phase)


def test_timeline_spec_metadata():
    spec = TimelineBlockSpec()
    assert spec.kind == "timeline"
    assert spec.template_path == "blocks/timeline.html"


def test_default_temporal_phase_is_past():
    e = TimelineEntry(title="x")
    assert e.temporal_phase == "past"


def test_minimum_viable_requires_two_entries_and_two_phases():
    spec = TimelineBlockSpec()
    one = TimelineBlockData(entries=[_entry()])
    two_same = TimelineBlockData(entries=[_entry("a", "past"), _entry("b", "past")])
    two_diff = TimelineBlockData(entries=[_entry("a", "past"), _entry("b", "present")])
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(two_same) is False
    assert spec.is_minimum_viable(two_diff) is True
