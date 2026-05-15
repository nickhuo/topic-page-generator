from generator.blocks.schema import (
    ChartBlockData,
    ChartStat,
    ChartSeries,
    ComparisonRow,
    ComparisonTable,
)
from generator.blocks.specs.chart import ChartBlockSpec


def test_chart_spec_metadata():
    spec = ChartBlockSpec()
    assert spec.kind == "chart"
    assert spec.template_path == "blocks/chart.html"


def test_chart_stat_minimum_viable():
    spec = ChartBlockSpec()
    empty = ChartBlockData(chart_type="stat", stats=[])
    one = ChartBlockData(
        chart_type="stat",
        stats=[ChartStat(value="42", label="Goals")],
    )
    assert spec.is_minimum_viable(empty) is False
    assert spec.is_minimum_viable(one) is True


def test_chart_bar_minimum_viable_needs_series():
    spec = ChartBlockSpec()
    no_series = ChartBlockData(chart_type="bar")
    with_series = ChartBlockData(
        chart_type="bar", series=[ChartSeries(label="A", values=[1.0, 2.0])]
    )
    assert spec.is_minimum_viable(no_series) is False
    assert spec.is_minimum_viable(with_series) is True


def test_chart_compare_table_minimum_viable():
    spec = ChartBlockSpec()
    empty = ChartBlockData(chart_type="compare_table")
    full = ChartBlockData(
        chart_type="compare_table",
        table=ComparisonTable(
            subjects=["A", "B"], rows=[ComparisonRow(axis="x", cells=["1", "2"])]
        ),
    )
    assert spec.is_minimum_viable(empty) is False
    assert spec.is_minimum_viable(full) is True
