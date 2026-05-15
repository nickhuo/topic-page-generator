"""Schema-roundtrip smoke tests."""

from __future__ import annotations

from generator.schema import EventPage


def _minimal_page_dict() -> dict:
    return {
        "page_id": "page_test",
        "input_sentence": "Test event happened.",
        "generated_at": "2026-05-13T12:00:00Z",
        "subject": {
            "title": "Test Entity launch",
            "subtitle": "Test Entity unveiled a new product.",
            "entities": ["Test Entity"],
            "when": "2026-05-01T00:00:00Z",
        },
        "editorial_sections": [],
        "layout": {"preset_id": "product_focus"},
        "sources": [
            {
                "id": "src_001",
                "url": "https://example.com/a",
                "publisher": {"name": "Example", "tier": "T0"},
                "title": "Example article",
                "published_at": "2026-05-01T00:00:00Z",
                "fetched_at": "2026-05-13T12:00:00Z",
                "language": "en",
                "rights": {"max_excerpt_words": 10000, "can_paraphrase": True},
            }
        ],
        "meta": {
            "last_updated": "2026-05-13T12:00:00Z",
            "editor_approved": True,
            "pipeline_trace_id": "trace_test",
        },
    }


def test_event_page_roundtrip() -> None:
    data = _minimal_page_dict()
    page = EventPage.model_validate(data)
    redump = page.model_dump(mode="json", exclude_none=True)
    # Roundtrip back through validation must succeed.
    EventPage.model_validate(redump)
    assert page.layout.preset_id == "product_focus"
    assert page.editorial_sections == []


def test_stage_trace_accepts_llm_calls():
    from generator.schema import StageTrace, LLMCall

    st = StageTrace(
        stage="ground",
        started_at="2026-05-13T12:00:00Z",
        duration_ms=120,
        outcome="success",
        llm_calls=[
            LLMCall(
                model="anthropic/claude-haiku-4-5",
                input_tokens=512,
                output_tokens=128,
                cost_usd=0.0011,
                duration_ms=110,
            )
        ],
    )
    assert st.llm_calls[0].model == "anthropic/claude-haiku-4-5"


def test_event_page_requires_editorial_sections() -> None:
    import pytest
    from pydantic import ValidationError

    data = _minimal_page_dict()
    del data["editorial_sections"]
    with pytest.raises(ValidationError):
        EventPage.model_validate(data)


def test_source_has_no_serves_needs_field() -> None:
    from generator.schema import Source, Publisher, SourceRights

    s = Source(
        id="s1",
        url="https://example.com/a",
        publisher=Publisher(name="P", tier="T0"),
        title="T",
        published_at="2026-05-01T00:00:00Z",
        fetched_at="2026-05-01T00:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=999, can_paraphrase=True),
    )
    assert not hasattr(s, "serves_needs")


def test_source_has_serves_sections_field() -> None:
    from generator.schema import Source, Publisher, SourceRights

    s = Source(
        id="s1",
        url="https://example.com/a",
        publisher=Publisher(name="P", tier="T0"),
        title="T",
        published_at="2026-05-01T00:00:00Z",
        fetched_at="2026-05-01T00:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=999, can_paraphrase=True),
        serves_sections=["overview"],
    )
    assert s.serves_sections == ["overview"]
