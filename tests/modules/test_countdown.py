"""Tests for the countdown module: schema binding, render gate, registry."""

from generator.modules import MODULE_REGISTRY
from generator.modules.countdown import CountdownModule
from generator.schema import CountdownData


def test_countdown_registered():
    assert MODULE_REGISTRY["countdown"] is CountdownModule


def test_countdown_metadata():
    assert CountdownModule.kind == "countdown"
    assert CountdownModule.serves_needs == ["what_next"]
    assert "Countdown" in CountdownModule.allowed_artifacts
    assert CountdownModule.data_schema is CountdownData
    assert isinstance(CountdownModule.extraction_prompt_template, str)
    assert "{primary_entity}" in CountdownModule.extraction_prompt_template
    assert "{evidence_block}" in CountdownModule.extraction_prompt_template


def test_countdown_should_render():
    data = CountdownData(
        target_at="2025-06-01T20:00:00Z", label="Game 1 tip-off", source_id="s1"
    )
    assert CountdownModule().should_render(data)


def test_countdown_should_render_none():
    assert not CountdownModule().should_render(None)
