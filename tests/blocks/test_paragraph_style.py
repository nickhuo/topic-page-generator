from generator.blocks.schema import ParagraphBlockData


def test_paragraph_style_defaults_to_prose():
    p = ParagraphBlockData(paragraphs_md=["x"])
    assert p.style == "prose"


def test_paragraph_style_bullets():
    p = ParagraphBlockData(paragraphs_md=["one", "two"], style="bullets")
    assert p.style == "bullets"
