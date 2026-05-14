"""Tests for the background module: schema binding, render gate, registry."""
from generator.modules import MODULE_REGISTRY
from generator.modules.background import BackgroundModule
from generator.schema import BackgroundData, BackgroundParagraph, Citation


def test_background_registered():
    assert MODULE_REGISTRY["background"] is BackgroundModule


def test_background_metadata():
    assert BackgroundModule.kind == "background"
    assert "what_happened" in BackgroundModule.serves_needs
    assert "why_matters" in BackgroundModule.serves_needs
    assert "Prose" in BackgroundModule.allowed_artifacts
    assert BackgroundModule.data_schema is BackgroundData
    assert isinstance(BackgroundModule.extraction_prompt_template, str)
    assert "{primary_entity}" in BackgroundModule.extraction_prompt_template
    assert "{evidence_block}" in BackgroundModule.extraction_prompt_template
    # Verify the mandated special prompt text is present
    assert "Synthesize 1" in BackgroundModule.extraction_prompt_template
    assert "Wikipedia" in BackgroundModule.extraction_prompt_template


def _make_paragraph(cited: bool = True) -> BackgroundParagraph:
    citations = [Citation(source_id="s1", claim_text="Fact A")] if cited else []
    return BackgroundParagraph(text="Some background text.", citations=citations)


def test_background_should_render():
    data = BackgroundData(paragraphs=[_make_paragraph(cited=True)])
    assert BackgroundModule().should_render(data)


def test_background_should_not_render_uncited():
    data = BackgroundData(paragraphs=[_make_paragraph(cited=False)])
    assert not BackgroundModule().should_render(data)


def test_background_should_render_none():
    assert not BackgroundModule().should_render(None)
