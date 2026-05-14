"""Tests for the official_statements module: schema binding, render gate, registry."""
from generator.modules import MODULE_REGISTRY
from generator.modules.official_statements import OfficialStatementsModule
from generator.schema import OfficialStatementsData, OfficialStatementItem


def test_official_statements_registered():
    assert MODULE_REGISTRY["official_statements"] is OfficialStatementsModule


def test_official_statements_metadata():
    assert OfficialStatementsModule.kind == "official_statements"
    assert OfficialStatementsModule.serves_needs == ["who_involved"]
    assert "StatementsList" in OfficialStatementsModule.allowed_artifacts
    assert OfficialStatementsModule.data_schema is OfficialStatementsData
    assert isinstance(OfficialStatementsModule.extraction_prompt_template, str)
    assert "{primary_entity}" in OfficialStatementsModule.extraction_prompt_template
    assert "{evidence_block}" in OfficialStatementsModule.extraction_prompt_template


def _make_item() -> OfficialStatementItem:
    return OfficialStatementItem(
        author="Jane Smith",
        role="Secretary of State",
        organization="US Department of State",
        quote="We are committed to dialogue.",
        made_at="2025-01-01T14:00:00Z",
        source_url="https://state.gov/press/release/1",
        source_id="s1",
    )


def test_official_statements_should_render():
    data = OfficialStatementsData(items=[_make_item()])
    assert OfficialStatementsModule().should_render(data)


def test_official_statements_should_not_render_empty():
    data = OfficialStatementsData(items=[])
    assert not OfficialStatementsModule().should_render(data)


def test_official_statements_should_render_none():
    assert not OfficialStatementsModule().should_render(None)
