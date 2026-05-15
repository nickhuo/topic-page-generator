"""Tests for the changelog module: schema binding, render gate, registry."""

from generator.modules import MODULE_REGISTRY
from generator.modules.changelog import ChangelogModule
from generator.schema import ChangelogData, ChangelogEntry


def test_changelog_registered():
    assert MODULE_REGISTRY["changelog"] is ChangelogModule


def test_changelog_metadata():
    assert ChangelogModule.kind == "changelog"
    assert "what_happened" in ChangelogModule.serves_needs
    assert "why_matters" in ChangelogModule.serves_needs
    assert "Changelog" in ChangelogModule.allowed_artifacts
    assert ChangelogModule.data_schema is ChangelogData
    assert isinstance(ChangelogModule.extraction_prompt_template, str)
    assert "{title}" in ChangelogModule.extraction_prompt_template
    assert "{evidence_block}" in ChangelogModule.extraction_prompt_template


def _make_entry() -> ChangelogEntry:
    return ChangelogEntry(
        label="New feature", description="Added X", importance="feature", source_id="s1"
    )


def test_changelog_should_render():
    data = ChangelogData(version_label="v2.0", entries=[_make_entry()])
    assert ChangelogModule().should_render(data)


def test_changelog_should_not_render_empty():
    data = ChangelogData(version_label="v2.0", entries=[])
    assert not ChangelogModule().should_render(data)


def test_changelog_should_render_none():
    assert not ChangelogModule().should_render(None)
