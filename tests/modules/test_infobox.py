"""Tests for the infobox module: schema binding, render gate, registry."""

from generator.modules import MODULE_REGISTRY
from generator.modules.infobox import InfoboxModule
from generator.schema import InfoboxData, InfoboxRow


def test_infobox_registered():
    assert MODULE_REGISTRY["infobox"] is InfoboxModule


def test_infobox_metadata():
    assert InfoboxModule.kind == "infobox"
    assert "when_where" in InfoboxModule.serves_needs
    assert "who_involved" in InfoboxModule.serves_needs
    assert "Infobox" in InfoboxModule.allowed_artifacts
    assert InfoboxModule.data_schema is InfoboxData
    assert isinstance(InfoboxModule.extraction_prompt_template, str)
    assert "{primary_entity}" in InfoboxModule.extraction_prompt_template
    assert "{evidence_block}" in InfoboxModule.extraction_prompt_template


def _make_row(
    label: str = "Key", value: str = "Val", source_id: str = "s1"
) -> InfoboxRow:
    return InfoboxRow(label=label, value=value, source_id=source_id)


def test_infobox_should_render_with_enough_rows():
    rows = [_make_row(label=f"K{i}") for i in range(3)]
    data = InfoboxData(rows=rows)
    assert InfoboxModule().should_render(data)


def test_infobox_should_not_render_with_too_few_rows():
    rows = [_make_row(label=f"K{i}") for i in range(2)]
    data = InfoboxData(rows=rows)
    assert not InfoboxModule().should_render(data)


def test_infobox_should_render_none():
    assert not InfoboxModule().should_render(None)
