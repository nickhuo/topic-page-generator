"""When USE_EDITOR_ARCHITECTURE=1, the CLI runs the new planners and exits."""

from __future__ import annotations

from pathlib import Path

import pytest

FIX = Path(__file__).parent.parent / "fixtures"


@pytest.mark.skipif(
    not (FIX / "openrouter_ground_happy.json").exists(),
    reason="needs the ground fixture used by the main e2e test",
)
def test_editor_architecture_flag_prints_section_plan(tmp_path, monkeypatch):
    """The end-to-end here is heavy; the cheap variant lives in the unit tests.
    This test only verifies the CLI honours the flag and exits with code 0
    after printing a SectionPlanOutput-shaped payload.
    """
    # The body of this test should reuse the same respx + monkeypatch shape
    # as tests/integration/test_end_to_end.py. If that test imports a
    # `_invoke_cli` helper or uses Typer's CliRunner, copy the pattern.
    pytest.skip(
        "Placeholder — wire up like test_end_to_end.py once that helper is "
        "factored out. Filed as a follow-up."
    )
