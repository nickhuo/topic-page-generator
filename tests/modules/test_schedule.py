"""Tests for the schedule module: schema binding, render gate, registry."""

from generator.modules import MODULE_REGISTRY
from generator.modules.schedule import ScheduleModule
from generator.schema import ScheduleData, ScheduleItem


def test_schedule_registered():
    assert MODULE_REGISTRY["schedule"] is ScheduleModule


def test_schedule_metadata():
    assert ScheduleModule.kind == "schedule"
    assert "when_where" in ScheduleModule.serves_needs
    assert "what_next" in ScheduleModule.serves_needs
    assert "ScheduleList" in ScheduleModule.allowed_artifacts
    assert ScheduleModule.data_schema is ScheduleData
    assert isinstance(ScheduleModule.extraction_prompt_template, str)
    assert "{primary_entity}" in ScheduleModule.extraction_prompt_template
    assert "{evidence_block}" in ScheduleModule.extraction_prompt_template


def _make_item() -> ScheduleItem:
    return ScheduleItem(
        time_iso="2025-01-01T10:00:00Z", label="Opening", source_id="s1"
    )


def test_schedule_should_render():
    data = ScheduleData(items=[_make_item()], timezone="America/New_York")
    assert ScheduleModule().should_render(data)


def test_schedule_should_not_render_empty_items():
    data = ScheduleData(items=[], timezone="America/New_York")
    assert not ScheduleModule().should_render(data)


def test_schedule_should_not_render_missing_timezone():
    data = ScheduleData(items=[_make_item()], timezone="")
    assert not ScheduleModule().should_render(data)


def test_schedule_should_render_none():
    assert not ScheduleModule().should_render(None)
