from generator.blocks.schema import FactsheetBlockData, FactsheetRow
from generator.blocks.specs.factsheet import FactsheetBlockSpec


def test_factsheet_spec_metadata():
    spec = FactsheetBlockSpec()
    assert spec.kind == "factsheet"
    assert spec.template_path == "blocks/factsheet.html"


def test_factsheet_minimum_viable_three_rows():
    spec = FactsheetBlockSpec()
    short = FactsheetBlockData(rows=[FactsheetRow(label="x", value="1")])
    full = FactsheetBlockData(
        rows=[
            FactsheetRow(label="a", value="1"),
            FactsheetRow(label="b", value="2"),
            FactsheetRow(label="c", value="3"),
        ]
    )
    assert spec.is_minimum_viable(short) is False
    assert spec.is_minimum_viable(full) is True
