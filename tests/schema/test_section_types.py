"""Tests for the new section-level schema primitives."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from generator.schema import (
    AcceptanceCriteria,
    SectionPlan,
    SectionPlanOutput,
    RenderedSection,
)
from generator.blocks.schema import ParagraphBlockData


def test_backbone_section_id_is_closed_enum():
    valid = {
        "overview",
        "timeline",
        "media_coverage",
        "latest_news",
    }
    for sid in valid:
        sp = SectionPlan(
            section_id=sid,
            kind="backbone",
            title="t",
            rank=1,
            block_kind="paragraph",
            intent="i",
            acceptance=AcceptanceCriteria(description="d"),
        )
        assert sp.section_id == sid


def test_acceptance_criteria_defaults():
    a = AcceptanceCriteria(description="cover who/what/when")
    assert a.min_sources == 1
    assert a.min_publishers == 1
    assert a.required_facets == []


def test_section_plan_curated_requires_string_section_id():
    sp = SectionPlan(
        section_id="people_relationships",
        kind="curated",
        title="Key people",
        rank=5,
        block_kind="paragraph",
        intent="who is involved and how",
        acceptance=AcceptanceCriteria(description="≥3 people"),
    )
    assert sp.kind == "curated"
    assert sp.section_id == "people_relationships"


def test_section_plan_rejects_unknown_block_kind():
    with pytest.raises(ValidationError):
        SectionPlan(
            section_id="overview",
            kind="backbone",
            title="t",
            rank=1,
            block_kind="not_a_real_kind",  # type: ignore[arg-type]
            intent="i",
            acceptance=AcceptanceCriteria(description="d"),
        )


def test_section_plan_output_orders_by_rank_field_not_position():
    out = SectionPlanOutput(
        sections=[
            SectionPlan(
                section_id="media_coverage",
                kind="backbone",
                title="m",
                rank=4,
                block_kind="newsfeed",
                intent="i",
                acceptance=AcceptanceCriteria(description="d"),
            ),
            SectionPlan(
                section_id="overview",
                kind="backbone",
                title="o",
                rank=1,
                block_kind="paragraph",
                intent="i",
                acceptance=AcceptanceCriteria(description="d"),
            ),
        ]
    )
    assert [s.section_id for s in out.sections] == ["media_coverage", "overview"]
    assert [s.rank for s in out.sections] == [4, 1]


def test_rendered_section_round_trip():
    block = ParagraphBlockData(paragraphs_md=["Hello."])
    rs = RenderedSection(
        section_id="overview",
        block_kind="paragraph",
        block_data=block,
        citations=[],
        sources_used=[],
        eval_passed=True,
        eval_notes=None,
    )
    assert rs.block_data.paragraphs_md == ["Hello."]
    assert rs.eval_passed is True
    assert rs.placement == "main"


def test_section_plan_placement_defaults_to_main_and_accepts_sidebar():
    sp_default = SectionPlan(
        section_id="overview",
        kind="backbone",
        title="t",
        rank=1,
        block_kind="paragraph",
        intent="i",
        acceptance=AcceptanceCriteria(description="d"),
    )
    assert sp_default.placement == "main"

    sp_side = SectionPlan(
        section_id="timeline",
        kind="backbone",
        title="t",
        rank=2,
        block_kind="timeline",
        intent="i",
        acceptance=AcceptanceCriteria(description="d"),
        placement="sidebar",
    )
    assert sp_side.placement == "sidebar"


def test_rendered_section_rejects_unknown_placement():
    with pytest.raises(ValidationError):
        RenderedSection(
            section_id="overview",
            block_kind="paragraph",
            block_data=ParagraphBlockData(paragraphs_md=["x"]),
            placement="footer",  # type: ignore[arg-type]
        )
