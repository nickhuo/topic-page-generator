"""Prompt builder for the block-extract LLM call.

For each SectionPlan, we compose:
  BASE_PREAMBLE + spec.extraction_prompt_fragment + section context + evidence

The model's response_format is `spec.data_schema` (a Pydantic block-data
class). The CLI-side stage post-validates citations against the per-section
evidence pool.

For gallery sections, an optional IMAGE_MANIFEST is injected above the
evidence block. Each item lists image_url, source_url, publisher, and title
so the LLM can pick and caption images by copying image_url verbatim.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from generator.blocks.specs.base import BlockSpec
from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import SectionPlan, Source

if TYPE_CHECKING:
    from generator.pipeline.block_extract import PersonImage
    from generator.sources.brave import BraveImageResult


def _format_evidence_block(sources: list[Source]) -> str:
    if not sources:
        return "(no evidence)"
    lines = []
    for s in sources:
        thumb_line = f"  image_url: {s.thumbnail_url}\n" if s.thumbnail_url else ""
        line = (
            f'<src id="{s.id}" tier="{s.publisher.tier}" '
            f'publisher="{s.publisher.name}" '
            f'url="{s.url}" published="{s.published_at}">\n'
            f"  title: {s.title}\n"
            f"{thumb_line}"
            f"  summary: {(s.summary or '')[:480]}\n"
            f"</src>"
        )
        lines.append(line)
    return "\n".join(lines)


def _format_image_manifest(images: list[BraveImageResult]) -> str:
    """Serialize a list of BraveImageResult into a numbered IMAGE_MANIFEST block."""
    lines = ["<image_manifest>"]
    for i, img in enumerate(images, start=1):
        lines.append(f"[{i}] image_url: {img.image_url}")
        if img.source_url:
            lines.append(f"    source_url: {img.source_url}")
        if img.publisher:
            lines.append(f"    publisher: {img.publisher}")
        if img.title:
            lines.append(f"    title: {img.title}")
    lines.append("</image_manifest>")
    return "\n".join(lines)


def _format_people_manifest(people: list[PersonImage]) -> str:
    """Serialize resolved person portraits for the LLM to copy verbatim.

    Used by `people` (PersonCard.image_url) and `reactions`
    (QuoteCard.author_image_url). The LLM MUST NOT invent URLs — only use
    values from this manifest, or omit the image field entirely.
    """
    if not people:
        return (
            "<people_image_manifest>\n"
            "  (no portraits resolved — leave image fields empty)\n"
            "</people_image_manifest>"
        )
    lines = ["<people_image_manifest>"]
    for p in people:
        lines.append(f'- name: "{p.name}"')
        lines.append(f"  image_url: {p.image_url}")
        if p.profile_url:
            lines.append(f"  profile_url: {p.profile_url}")
        lines.append(f"  image_source: {p.image_source}")
    lines.append("</people_image_manifest>")
    return "\n".join(lines)


def build_block_extract_messages(
    *,
    section: SectionPlan,
    spec: type[BlockSpec],
    sources: list[Source],
    canonical_title: str,
    image_manifest: list[BraveImageResult] | None = None,
    people_manifest: list[PersonImage] | None = None,
    editor_note: str | None = None,
) -> list[dict]:
    evidence_block = _format_evidence_block(sources)

    manifest_block = ""
    if image_manifest is not None:
        manifest_block = _format_image_manifest(image_manifest) + "\n\n"
    if people_manifest is not None:
        manifest_block += _format_people_manifest(people_manifest) + "\n\n"

    editor_line = ""
    if editor_note:
        editor_line = (
            f"EDITOR_NOTE: {editor_note}\n"
            "(Treat EDITOR_NOTE as a hard editorial constraint that overrides "
            "earlier instructions unless following it would invalidate citation integrity.)\n\n"
        )

    user = (
        f"CANONICAL_TITLE: {canonical_title}\n"
        f"SECTION_ID: {section.section_id}\n"
        f"SECTION_TITLE: {section.title}\n"
        f"INTENT: {section.intent}\n"
        f"ACCEPTANCE: {section.acceptance.description}\n"
        f"BLOCK_KIND: {section.block_kind}\n"
        f"\n{editor_line}"
        f"{manifest_block}"
        f"<evidence>\n{evidence_block}\n</evidence>\n"
        f"\nOUTPUT a {section.block_kind} block JSON now."
    )
    return [
        {
            "role": "system",
            "content": (BASE_PREAMBLE + "\n\n" + spec.extraction_prompt_fragment),
        },
        {"role": "user", "content": user},
    ]


__all__ = ["build_block_extract_messages"]
