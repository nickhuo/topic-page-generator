"""Tests for the kpi_numbers module: schema binding, render gate, registry."""
from generator.modules import MODULE_REGISTRY
from generator.modules.kpi_numbers import KPINumbersModule
from generator.schema import KPINumbersData, KPITile


def test_kpi_numbers_registered():
    assert MODULE_REGISTRY["kpi_numbers"] is KPINumbersModule


def test_kpi_numbers_metadata():
    assert KPINumbersModule.kind == "kpi_numbers"
    assert "current_state" in KPINumbersModule.serves_needs
    assert "why_matters" in KPINumbersModule.serves_needs
    assert "KPITiles" in KPINumbersModule.allowed_artifacts
    assert KPINumbersModule.data_schema is KPINumbersData
    assert isinstance(KPINumbersModule.extraction_prompt_template, str)
    assert "{primary_entity}" in KPINumbersModule.extraction_prompt_template
    assert "{evidence_block}" in KPINumbersModule.extraction_prompt_template


def _make_tile(label: str = "Revenue") -> KPITile:
    return KPITile(value="1B", unit="USD", label=label, source_id="s1")


def test_kpi_numbers_should_render_one_tile():
    data = KPINumbersData(tiles=[_make_tile()])
    assert KPINumbersModule().should_render(data)


def test_kpi_numbers_should_render_four_tiles():
    data = KPINumbersData(tiles=[_make_tile(label=f"L{i}") for i in range(4)])
    assert KPINumbersModule().should_render(data)


def test_kpi_numbers_should_render_none():
    assert not KPINumbersModule().should_render(None)
