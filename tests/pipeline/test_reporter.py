"""Smoke tests for the pipeline reporter."""

from __future__ import annotations

import io

from rich.console import Console

from generator.pipeline.reporter import NullReporter, RichReporter


def test_null_reporter_is_silent():
    r = NullReporter()
    with r.stage("research"):
        r.section_event("a", "query_generated", iter=1, query="q")
        r.section_event("a", "pool_grew", new=2, total=2)
        r.section_event("a", "eval_satisfied")
        r.note("hi")
        r.warn("oops", reason="x")


def test_rich_reporter_emits_to_console_outside_live():
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    r = RichReporter(console)
    with r.stage("research"):
        r.section_event("sec_a", "extract_dropped", reason="below_threshold")
        r.note("curation kept 3")
        r.warn("brave miss", reason="no_key")
    out = buf.getvalue()
    assert "research" in out
    assert "sec_a" in out
    assert "below_threshold" in out
    assert "curation kept 3" in out
    assert "brave miss" in out


def test_rich_reporter_live_table_non_terminal_does_not_block():
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, width=120)
    r = RichReporter(console)
    with r.live_section_table(["a", "b"]):
        r.section_event("a", "query_generated", iter=1, query="hello")
        r.section_event("a", "pool_grew", new=1, total=1)
        r.section_event("b", "cap_hit")
    # On non-TTY, Live is skipped — but state still updates; no crashes.
    # We just confirm it returned cleanly.
