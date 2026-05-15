from generator.blocks.schema import ParagraphBlockData
from generator.blocks.specs.paragraph import ParagraphBlockSpec


def test_paragraph_spec_metadata():
    spec = ParagraphBlockSpec()
    assert spec.kind == "paragraph"
    assert spec.data_schema is ParagraphBlockData
    assert spec.template_path == "blocks/paragraph.html"
    assert "paragraphs_md" in spec.extraction_prompt_fragment


def test_paragraph_minimum_viable_empty_fails():
    spec = ParagraphBlockSpec()
    data = ParagraphBlockData(paragraphs_md=["   "])
    assert spec.is_minimum_viable(data) is False


def test_paragraph_minimum_viable_ok():
    spec = ParagraphBlockSpec()
    data = ParagraphBlockData(paragraphs_md=["A real sentence."])
    assert spec.is_minimum_viable(data) is True
