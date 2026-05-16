"""Integration test for the ``regen-section`` CLI subcommand."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from generator.cli import app
from generator.schema import (
    EventLayout,
    EventMeta,
    EventPage,
    EventSubject,
    RenderedSection,
    Source,
    Trace,
    TraceApproval,
    StageTrace,
)
from generator.blocks.schema import ParagraphBlockData


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_source(source_id: str = "s1") -> Source:
    return Source(
        id=source_id,
        url="https://example.com/article",
        publisher={"name": "Example News", "tier": "T1"},
        title="Example article",
        published_at="2026-05-01T00:00:00+00:00",
        fetched_at="2026-05-01T00:01:00+00:00",
        language="en",
        rights={"max_excerpt_words": 100, "can_paraphrase": True},
    )


def _make_rendered_section(section_id: str = "overview") -> RenderedSection:
    block = ParagraphBlockData(
        kind="paragraph",
        style="prose",
        paragraphs_md=["An overview paragraph."],
    )
    return RenderedSection(
        section_id=section_id,
        block_kind="paragraph",
        block_data=block,
        citations=[],
        sources_used=[_make_source()],
        eval_passed=True,
    )


def _make_page(sections: list[RenderedSection] | None = None) -> EventPage:
    if sections is None:
        sections = [_make_rendered_section("overview")]
    return EventPage(
        page_id="page_test01",
        input_sentence="test event for regen-section",
        generated_at="2026-05-01T00:00:00+00:00",
        subject=EventSubject(
            title="Test Event", subtitle="Test subtitle.", entities=["Test Entity"]
        ),
        layout=EventLayout(preset_id="product_focus", overrides=None),
        sources=[_make_source()],
        editorial_sections=sections,
        meta=EventMeta(
            last_updated="2026-05-01T00:00:00+00:00",
            editor_approved=True,
            editor_id="cli_user@local",
            pipeline_trace_id="tr_test01",
        ),
    )


def _make_trace() -> Trace:
    return Trace(
        trace_id="tr_test01",
        page_id="page_test01",
        input_sentence="test event for regen-section",
        started_at="2026-05-01T00:00:00+00:00",
        ended_at="2026-05-01T00:01:00+00:00",
        total_duration_ms=60_000,
        total_cost_usd=0.01,
        pipeline_trace=[
            StageTrace(
                stage="ground",
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


@pytest.fixture()
def demo_files(tmp_path: Path):
    """Write demo.data.json + demo.trace.json; return (data_path, trace_path)."""
    page = _make_page()
    data_path = tmp_path / "demo.data.json"
    trace_path = tmp_path / "demo.trace.json"
    data_path.write_text(page.model_dump_json(indent=2), encoding="utf-8")
    trace_path.write_text(_make_trace().model_dump_json(indent=2), encoding="utf-8")
    return data_path, trace_path


# ---------------------------------------------------------------------------
# Patching helpers
# ---------------------------------------------------------------------------


def _patch_extract_one_section(monkeypatch, new_section: RenderedSection | None = None):
    """Monkeypatch extract_one_section to return `new_section` (or a copy of overview)."""
    if new_section is None:
        new_section = _make_rendered_section("overview")

    async def _fake(*, section, sources, canonical_title, model=None):
        return new_section

    monkeypatch.setattr("generator.pipeline.block_extract.extract_one_section", _fake)
    # Also patch the import in cli.py's local scope — cli.py imports inside the function
    # so we patch the source module only.


def _patch_render_html(monkeypatch):
    monkeypatch.setattr("generator.pipeline.render.render_html", lambda page: "<html/>")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRegenSection:
    def test_exit_code_zero(self, demo_files, monkeypatch):
        """Happy path: command exits 0."""
        data_path, _ = demo_files
        _patch_extract_one_section(monkeypatch)
        _patch_render_html(monkeypatch)

        runner = CliRunner()
        result = runner.invoke(app, ["regen-section", "overview", str(data_path)])
        assert result.exit_code == 0, result.output
        assert "Regenerated section overview" in result.output

    def test_data_json_updated(self, demo_files, monkeypatch):
        """The target section must be replaced in the re-written data.json."""
        data_path, _ = demo_files
        new_block = ParagraphBlockData(
            kind="paragraph",
            style="prose",
            paragraphs_md=["REGEN_SENTINEL paragraph."],
        )
        new_section = RenderedSection(
            section_id="overview",
            block_kind="paragraph",
            block_data=new_block,
            citations=[],
            sources_used=[],
            eval_passed=True,
        )
        _patch_extract_one_section(monkeypatch, new_section)
        _patch_render_html(monkeypatch)

        runner = CliRunner()
        result = runner.invoke(app, ["regen-section", "overview", str(data_path)])
        assert result.exit_code == 0, result.output

        updated = json.loads(data_path.read_text())
        sections = updated["editorial_sections"]
        overview = next(s for s in sections if s["section_id"] == "overview")
        assert overview["block_data"]["paragraphs_md"] == ["REGEN_SENTINEL paragraph."]

    def test_html_file_written(self, demo_files, monkeypatch):
        """An .html file must be written alongside the data.json."""
        data_path, _ = demo_files
        html_path = data_path.parent / "demo.html"
        _patch_extract_one_section(monkeypatch)
        _patch_render_html(monkeypatch)

        runner = CliRunner()
        result = runner.invoke(app, ["regen-section", "overview", str(data_path)])
        assert result.exit_code == 0, result.output
        assert html_path.exists(), "Expected demo.html to be created"

    def test_trace_json_action_appended(self, demo_files, monkeypatch):
        """A regenerate_section action must be appended to trace.json."""
        data_path, trace_path = demo_files
        _patch_extract_one_section(monkeypatch)
        _patch_render_html(monkeypatch)

        before = Trace.model_validate_json(trace_path.read_text())
        assert len(before.editor_actions) == 0

        runner = CliRunner()
        result = runner.invoke(app, ["regen-section", "overview", str(data_path)])
        assert result.exit_code == 0, result.output

        after_raw = json.loads(trace_path.read_text())
        actions = after_raw.get("editor_actions", [])
        assert len(actions) == 1
        assert actions[0]["action"] == "regenerate_section"
        assert actions[0]["target"]["section_id"] == "overview"

    def test_unknown_section_id_exits_nonzero(self, demo_files):
        """Requesting a section_id not in the page must exit non-zero."""
        data_path, _ = demo_files
        runner = CliRunner()
        result = runner.invoke(
            app, ["regen-section", "nonexistent_section", str(data_path)]
        )
        assert result.exit_code != 0
