"""Gallery block spec — image + caption cards.

Unlike text-only blocks, gallery extraction depends on an external image
search (Brave) performed BEFORE the LLM call. The spec only describes the
output shape; the orchestrator (block_extract.extract_one_section) is
responsible for fetching the image manifest and injecting it into the
prompt.
"""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import GalleryBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


class GalleryBlockSpec(BlockSpec):
    kind: ClassVar = "gallery"
    data_schema: ClassVar = GalleryBlockData
    template_path: ClassVar = "blocks/gallery.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description="At least 3 images, each with a one-sentence caption.",
        min_sources=0,  # images are sourced externally; text citations optional
        min_publishers=0,
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `gallery` block.

You will be given an IMAGE_MANIFEST listing candidate images with their source
URLs, publishers, and titles. Pick 3-8 of the most relevant images and write
a tight one-sentence caption for each.

Schema:
- items: 3-8 GalleryItem objects, each with:
    - image_url: the URL from the manifest, copied verbatim
    - caption: one declarative sentence (<=240 chars) describing what the image shows
      and why it matters for this section. No hedging, no "this is an image of".
    - alt_text: 5-12 words of accessibility text (literal description, no editorializing)
    - source_url: copied verbatim from the manifest if available
- citations: optional citations to TEXT evidence (source_id) that the caption draws from

Picking rules:
- Prefer images whose title/publisher matches the section's entity or event
- Skip stock-photo lookalikes, logos, or unrelated thumbnails
- Spread across 2+ distinct publishers when possible
- If fewer than 3 manifest items are usable, return as many as you have (the
  minimum-viable check on the spec side will drop the section if too thin)
"""

    def is_minimum_viable(self, data: GalleryBlockData) -> bool:
        return len(data.items) >= 2
