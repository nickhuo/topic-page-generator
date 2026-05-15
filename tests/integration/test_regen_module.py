"""Integration test for the ``regen-module`` CLI subcommand (Task 5)."""

from __future__ import annotations

import pytest

pytest.skip("regen-module removed; see test_regen_section.py", allow_module_level=True)

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from generator.cli import app
from generator.schema import (
    Trace,
    TraceApproval,
    StageTrace,
)
from tests.fixtures import make_full_event_page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_trace(page_id: str = "p1") -> Trace:
    """Construct a minimal valid Trace with no editor_actions."""
    return Trace(
        trace_id="tr1",
        page_id=page_id,
        input_sentence="x",
        started_at="2026-05-01T00:00:00+00:00",
        ended_at="2026-05-01T00:01:00+00:00",
        total_duration_ms=60_000,
        total_cost_usd=0.01,
        pipeline_trace=[
            StageTrace(
                stage="triage",
                started_at="2026-05-01T00:00:00+00:00",
                duration_ms=100,
                outcome="success",
            )
        ],
        editor_actions=[],
        final_outcome="approved_published",
        approval=TraceApproval(
            actor="cli_user@local",
            approved_at="2026-05-01T00:01:00+00:00",
            auto_mode=False,
        ),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def demo_files(tmp_path: Path):
    """Write demo.data.json + demo.trace.json to tmp_path and return their paths."""
    page = make_full_event_page()
    data_path = tmp_path / "demo.data.json"
    trace_path = tmp_path / "demo.trace.json"

    data_path.write_text(
        page.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
    )
    trace_obj = _make_trace(page_id=page.page_id)
    trace_path.write_text(
        trace_obj.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
    )

    return data_path, trace_path


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegenModule:
    def test_exit_code_zero(self, demo_files, monkeypatch):
        """Happy path: command exits 0 and prints success message."""
        data_path, _ = demo_files
        _patch_both(monkeypatch)

        runner = CliRunner()
        result = runner.invoke(app, ["regen-module", "reactions", str(data_path)])

        assert result.exit_code == 0, result.output
        assert "Regenerated module 'reactions'" in result.output

    def test_data_json_updated(self, demo_files, monkeypatch):
        """The named module must appear changed in the re-written data.json."""
        data_path, _ = demo_files

        # Load the typed module so we can copy it (bare Module classes are ABCs, not Pydantic).
        from generator.schema import EventPage as EP

        original_page = EP.model_validate_json(data_path.read_text())
        original_reactions = next(
            m for m in original_page.modules if m.kind == "reactions"
        )
        sentinel = original_reactions.model_copy(update={"artifact": "REGEN_SENTINEL"})

        called: list[bool] = []

        async def fake_extract(module, ctx, evidence, *, regen_feedback):
            called.append(True)
            return sentinel

        _patch_extract(monkeypatch, fake_extract)
        _patch_render_html(monkeypatch)

        runner = CliRunner()
        result = runner.invoke(app, ["regen-module", "reactions", str(data_path)])

        assert result.exit_code == 0, result.output
        assert called, "extract_one_module fake was never called"

        updated = json.loads(data_path.read_text())
        reactions_mod = next(m for m in updated["modules"] if m["kind"] == "reactions")
        assert reactions_mod["artifact"] == "REGEN_SENTINEL"

    def test_html_file_written(self, demo_files, monkeypatch):
        """An .html file must be written (or overwritten) alongside the data.json."""
        data_path, _ = demo_files
        html_path = data_path.parent / "demo.html"

        _patch_both(monkeypatch)

        runner = CliRunner()
        result = runner.invoke(app, ["regen-module", "reactions", str(data_path)])

        assert result.exit_code == 0, result.output
        assert html_path.exists(), "Expected demo.html to be created"

    def test_trace_json_action_appended(self, demo_files, monkeypatch):
        """One new ``regenerate_module`` EditorAction must be appended to trace.json."""
        data_path, trace_path = demo_files
        _patch_both(monkeypatch)

        # Confirm pre-condition: 0 editor actions.
        before = Trace.model_validate_json(trace_path.read_text())
        assert len(before.editor_actions) == 0

        runner = CliRunner()
        result = runner.invoke(app, ["regen-module", "reactions", str(data_path)])

        assert result.exit_code == 0, result.output

        after = Trace.model_validate_json(trace_path.read_text())
        assert len(after.editor_actions) == 1
        action = after.editor_actions[0]
        assert action.action == "regenerate_module"
        assert action.target is not None and action.target.module_kind == "reactions"

    def test_unknown_kind_exits_nonzero(self, demo_files):
        """Requesting a kind that doesn't exist in the page must exit non-zero."""
        data_path, _ = demo_files
        runner = CliRunner()
        result = runner.invoke(
            app, ["regen-module", "nonexistent_kind", str(data_path)]
        )
        assert result.exit_code != 0

    def test_trace_json_not_required(self, tmp_path, monkeypatch):
        """If trace.json is missing the command still succeeds (trace append is optional)."""
        page = make_full_event_page()
        data_path = tmp_path / "notrace.data.json"
        data_path.write_text(
            page.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
        )
        # No trace file written.

        _patch_both(monkeypatch)

        runner = CliRunner()
        result = runner.invoke(app, ["regen-module", "reactions", str(data_path)])
        assert result.exit_code == 0, result.output


# ---------------------------------------------------------------------------
# Private patching helpers
# ---------------------------------------------------------------------------


def _patch_extract(monkeypatch, fake_fn=None):
    """Monkeypatch extract_one_module in both the extract module and cli import.

    The default fake returns a synthetic ReactionsModule TypedModule so callers
    don't have to construct one themselves.
    """
    if fake_fn is None:
        from tests.fixtures import make_full_event_page

        _sentinel_page = make_full_event_page()
        _sentinel_reactions = next(
            m for m in _sentinel_page.modules if m.kind == "reactions"
        )
        _sentinel = _sentinel_reactions.model_copy(update={"artifact": "FAKE_REGEN"})

        async def fake_fn(module, ctx, evidence, *, regen_feedback):
            return _sentinel

    monkeypatch.setattr("generator.pipeline.extract.extract_one_module", fake_fn)
    monkeypatch.setattr("generator.cli.extract_one_module", fake_fn)


def _patch_render_html(monkeypatch):
    """Monkeypatch render_html so tests don't depend on Jinja templates."""
    monkeypatch.setattr("generator.pipeline.render.render_html", lambda page: "<html/>")


def _patch_both(monkeypatch, fake_extract=None):
    _patch_extract(monkeypatch, fake_extract)
    _patch_render_html(monkeypatch)
