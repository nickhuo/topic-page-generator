"""Tests for the comparison module: schema binding, render gate, registry."""

from generator.modules import MODULE_REGISTRY
from generator.modules.comparison import ComparisonModule
from generator.schema import (
    ComparisonData,
    ComparisonSubject,
    ComparisonAxis,
    ComparisonCell,
)


def test_comparison_registered():
    assert MODULE_REGISTRY["comparison"] is ComparisonModule


def test_comparison_metadata():
    assert ComparisonModule.kind == "comparison"
    assert "who_involved" in ComparisonModule.serves_needs
    assert "why_matters" in ComparisonModule.serves_needs
    assert "ComparisonTable" in ComparisonModule.allowed_artifacts
    assert ComparisonModule.data_schema is ComparisonData
    assert isinstance(ComparisonModule.extraction_prompt_template, str)
    assert "{primary_entity}" in ComparisonModule.extraction_prompt_template
    assert "{evidence_block}" in ComparisonModule.extraction_prompt_template


def _make_data(n_subjects: int = 2, n_axes: int = 1) -> ComparisonData:
    subjects = [ComparisonSubject(name=f"S{i}") for i in range(n_subjects)]
    axes = [
        ComparisonAxis(
            label=f"Axis{j}",
            cells=[
                ComparisonCell(value=f"v{i}{j}", source_id="s1")
                for i in range(n_subjects)
            ],
        )
        for j in range(n_axes)
    ]
    return ComparisonData(subjects=subjects, axes=axes)


def test_comparison_should_render():
    data = _make_data(n_subjects=2, n_axes=2)
    assert ComparisonModule().should_render(data)


def test_comparison_should_not_render_one_subject():
    # Can't create with 1 subject due to min_length=2, so test mismatched cells
    # Manually corrupt cells count to simulate mismatch
    from generator.schema import ComparisonSubject, ComparisonAxis, ComparisonCell

    subjects = [ComparisonSubject(name="A"), ComparisonSubject(name="B")]
    axes = [
        ComparisonAxis(label="X", cells=[ComparisonCell(value="v", source_id="s1")])
    ]  # 1 cell, 2 subjects
    bad_data = ComparisonData(subjects=subjects, axes=axes)
    assert not ComparisonModule().should_render(bad_data)


def test_comparison_should_render_none():
    assert not ComparisonModule().should_render(None)
