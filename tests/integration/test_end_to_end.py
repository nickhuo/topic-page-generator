"""Integration test: full pipeline in --auto mode with all LLM/fetch stages monkeypatched.

Strategy: monkeypatch each stage's module-level `run` / `run_*` function to return
canned high-confidence outputs. This avoids any real network traffic and is simpler
than mocking the HTTP layer when each stage expects a different JSON schema.
"""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from generator.cli import app
from generator.schema import (
    AestheticOverrides,
    AestheticPlanOutput,
    ConsistencyCheckOutput,
    DisambiguationChosen,
    DisambiguationOutput,
    TriageOutput,
)
from tests.fixtures import make_full_event_page, source


# ---------------------------------------------------------------------------
# Canned stage outputs (all confidence values > 0.85 so no HITL fires)
# ---------------------------------------------------------------------------

_TRIAGE = TriageOutput(
    is_event=True,
    primary_entity="Test Event",
    event_type_hint="product_launch",
    temporal_posture="recent",
    time_anchor="2026-05-14T00:00:00+00:00",
    confidence=0.95,
    alternatives=[],
    reasoning="canned triage for e2e test",
)

_DISAMB = DisambiguationOutput(
    resolved=True,
    chosen=DisambiguationChosen(
        entity="Test Event",
        event_type_hint="product_launch",
        time_anchor="2026-05-14T00:00:00+00:00",
        supporting_sources=[],
    ),
    unresolved_candidates=[],
)

_AESTHETIC = AestheticPlanOutput(
    preset_id="reference",
    preset_confidence=0.92,
    alternatives_considered=[],
    aesthetic_overrides=AestheticOverrides(),
    reasoning="canned aesthetic for e2e test",
)

_SOURCES = [
    source("s1", "https://example.com/a", "T0"),
    source("s2", "https://example.com/b", "T1"),
]

_CONSISTENCY = ConsistencyCheckOutput(passes=True, issues=[])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _patch_pipeline(monkeypatch, tmp_output_dir: Path) -> None:
    """Wire all LLM/fetch stage entrypoints to return canned data."""
    import generator.cli as cli_mod
    import generator.pipeline.triage as triage_mod
    import generator.pipeline.disambiguate as disamb_mod
    import generator.pipeline.plan as plan_mod
    import generator.pipeline.fetch as fetch_mod
    import generator.pipeline.extract as extract_mod
    import generator.pipeline.consistency as consistency_mod
    import generator.pipeline.render as render_mod

    # --- triage
    async def fake_triage(sentence, **kw):
        return _TRIAGE

    monkeypatch.setattr(triage_mod, "run", fake_triage)

    # --- disambiguate (already short-circuits at confidence>=0.85 but patch anyway)
    async def fake_disamb(triage, **kw):
        return _DISAMB

    monkeypatch.setattr(disamb_mod, "run", fake_disamb)

    # --- aesthetic plan (plan stage 3a is deterministic; patch only 3b LLM call)
    async def fake_aesthetic(triage, plan, evidence_preview, **kw):
        return _AESTHETIC

    monkeypatch.setattr(plan_mod, "run_aesthetic_stage", fake_aesthetic)

    # --- fetch
    async def fake_fetch(plan, subject, **kw):
        return list(_SOURCES)

    monkeypatch.setattr(fetch_mod, "run_fetch_stage", fake_fetch)
    monkeypatch.setattr(cli_mod, "run_fetch_stage", fake_fetch)

    # --- extract (return the full page's modules)
    _full_page = make_full_event_page()

    async def fake_extract(plan, aesthetic, subject, sources, **kw):
        return list(_full_page.modules)

    monkeypatch.setattr(extract_mod, "run", fake_extract)

    # --- consistency
    async def fake_consistency(modules, ctx, sources, **kw):
        needs = {
            n: []
            for n in [
                "what_happened",
                "when_where",
                "who_involved",
                "current_state",
                "why_matters",
                "world_reaction",
                "what_can_do",
                "what_next",
            ]
        }
        return _CONSISTENCY, list(modules), needs, []

    monkeypatch.setattr(consistency_mod, "run", fake_consistency)

    # --- render HTML (skip Jinja so no template path issues in test env)
    monkeypatch.setattr(
        render_mod, "render_html", lambda page: "<html><body>ok</body></html>"
    )

    # --- redirect output dir to tmp_path
    monkeypatch.setattr(cli_mod, "_OUTPUT_DIR", tmp_output_dir)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


class TestEndToEndAuto:
    def test_auto_mode_writes_three_artifacts_and_trace(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Full --auto run: exit 0, three output files, correct trace fields."""
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-dummy-key")
        monkeypatch.setenv("TAVILY_API_KEY", "test-dummy-key")

        tmp_output = tmp_path / "output"
        tmp_output.mkdir()
        _patch_pipeline(monkeypatch, tmp_output)

        runner = CliRunner()
        result = runner.invoke(
            app, ["run", "--auto", "Test event for end-to-end pipeline"]
        )

        assert result.exit_code == 0, result.output

        # Three output artifacts must exist
        html_files = list(tmp_output.glob("*.html"))
        data_files = list(tmp_output.glob("*.data.json"))
        trace_files = list(tmp_output.glob("*.trace.json"))

        assert html_files, "Expected at least one .html file in output dir"
        assert data_files, "Expected at least one .data.json file in output dir"
        assert trace_files, "Expected at least one .trace.json file in output dir"

        # All three should share the same slug
        assert html_files[0].stem == data_files[0].stem.removesuffix(".data")
        assert html_files[0].stem == trace_files[0].stem.removesuffix(".trace")

        # Trace assertions
        trace = json.loads(trace_files[0].read_text())
        assert trace["approval"]["auto_mode"] is True
        assert trace["final_outcome"] == "auto_approved"

        for action in trace.get("editor_actions", []):
            assert action.get("reason") == "auto_mode", f"non-auto reason: {action}"
