from generator.blocks.schema import TimelineBlockData, TimelineEntry
from generator.blocks.specs.timeline import TimelineBlockSpec


def _entry(title="t") -> TimelineEntry:
    return TimelineEntry(title=title, time="2026-05-15")


def test_timeline_spec_metadata():
    spec = TimelineBlockSpec()
    assert spec.kind == "timeline"
    assert spec.template_path == "blocks/timeline.html"


def test_timeline_minimum_viable_requires_two_entries():
    spec = TimelineBlockSpec()
    one = TimelineBlockData(entries=[_entry()])
    two = TimelineBlockData(entries=[_entry("a"), _entry("b")])
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(two) is True
