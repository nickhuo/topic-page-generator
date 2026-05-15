"""GalleryBlockSpec tests."""

from generator.blocks.schema import GalleryBlockData, GalleryItem
from generator.blocks.specs.gallery import GalleryBlockSpec


def _item(url="https://example.com/a.jpg") -> GalleryItem:
    return GalleryItem(image_url=url, caption="A photo of something.")


def test_gallery_spec_metadata():
    spec = GalleryBlockSpec()
    assert spec.kind == "gallery"
    assert spec.template_path == "blocks/gallery.html"
    assert "image_url" in spec.extraction_prompt_fragment
    assert "caption" in spec.extraction_prompt_fragment


def test_gallery_minimum_viable_requires_two_items():
    spec = GalleryBlockSpec()
    one = GalleryBlockData(items=[_item()])
    two = GalleryBlockData(items=[_item("https://a.com/1.jpg"), _item("https://a.com/2.jpg")])
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(two) is True


def test_gallery_block_data_round_trips():
    data = GalleryBlockData(
        items=[
            GalleryItem(
                image_url="https://example.com/1.jpg",
                caption="Wide shot of the stage at the keynote.",
                alt_text="Stage with the company logo behind a podium",
                source_url="https://example.com/article",
            )
        ]
    )
    dumped = data.model_dump()
    assert dumped["kind"] == "gallery"
    assert len(dumped["items"]) == 1
    GalleryBlockData.model_validate(dumped)  # round-trip
