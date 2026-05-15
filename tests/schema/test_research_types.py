"""Schema additions for the research loop."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from generator.schema import ResearchEvalResult, Source, Publisher, SourceRights


def test_research_eval_result_satisfied():
    r = ResearchEvalResult(satisfied=True, gaps=[], next_query_hint=None)
    assert r.satisfied is True
    assert r.gaps == []
    assert r.next_query_hint is None


def test_research_eval_result_unsatisfied_requires_gaps():
    """When satisfied=False, gaps must be non-empty — the LLM has to say why."""
    with pytest.raises(ValidationError):
        ResearchEvalResult(satisfied=False, gaps=[], next_query_hint=None)


def test_research_eval_result_unsatisfied_with_gaps():
    r = ResearchEvalResult(
        satisfied=False,
        gaps=["no source covers the timeline"],
        next_query_hint="GTC 2026 keynote timeline announcements",
    )
    assert r.satisfied is False
    assert len(r.gaps) >= 1


def test_source_serves_sections_defaults_to_empty():
    src = _source_factory()
    assert src.serves_sections == []


def test_source_serves_sections_roundtrip():
    src = _source_factory(serves_sections=["overview", "timeline"])
    assert src.serves_sections == ["overview", "timeline"]


def _source_factory(**overrides):
    base = dict(
        id="s1",
        url="https://example.com/a",
        publisher=Publisher(name="Example", tier="T1"),
        title="t",
        published_at="2026-05-15T12:00:00Z",
        fetched_at="2026-05-15T12:01:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )
    base.update(overrides)
    return Source(**base)
