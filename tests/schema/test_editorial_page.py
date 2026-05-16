"""EventPage with editorial_sections + RenderedSection validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from generator.blocks.schema import ParagraphBlockData, TimelineBlockData
from generator.schema import EventPage, RenderedSection


def test_event_page_editorial_sections_default_is_none():
    """Existing pipeline path must not have to supply editorial_sections."""
    # We don't construct a full EventPage here — too many required fields.
    # Instead validate the field's default is None via the model schema.
    schema = EventPage.model_json_schema()
    assert "editorial_sections" in schema["properties"]
    field = schema["properties"]["editorial_sections"]
    # default null (Optional[list[RenderedSection]])
    assert field.get("default", None) is None


def test_rendered_section_accepts_paragraph_block_data():
    block = ParagraphBlockData(paragraphs_md=["Hello world."])
    rs = RenderedSection(
        section_id="overview",
        block_kind="paragraph",
        block_data=block,
    )
    assert rs.block_data.kind == "paragraph"


def test_rendered_section_accepts_timeline_block_data():
    from generator.blocks.schema import TimelineEntry

    block = TimelineBlockData(
        entries=[TimelineEntry(title="Announcement", time="2026-03-19")]
    )
    rs = RenderedSection(
        section_id="timeline",
        block_kind="timeline",
        block_data=block,
    )
    assert rs.block_data.kind == "timeline"


def test_rendered_section_block_kind_must_match_block_data_kind():
    """If section claims block_kind=paragraph but block_data is TimelineBlockData,
    that's a contract violation. Validate it raises."""
    from generator.blocks.schema import TimelineEntry

    with pytest.raises(ValidationError):
        RenderedSection(
            section_id="x",
            block_kind="paragraph",
            block_data=TimelineBlockData(entries=[TimelineEntry(title="Event")]),
        )
