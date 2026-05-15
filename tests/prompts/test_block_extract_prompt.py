"""Block-extract prompt builder — composes spec fragment + section context + evidence."""

from __future__ import annotations

from generator.blocks.specs import get_spec
from generator.prompts.block_extract import build_block_extract_messages
from generator.schema import (
    AcceptanceCriteria,
    Publisher,
    SectionPlan,
    Source,
    SourceRights,
)


def _section(block_kind: str = "paragraph") -> SectionPlan:
    return SectionPlan(
        section_id="overview",
        kind="backbone",
        title="Overview",
        rank=1,
        block_kind=block_kind,  # type: ignore[arg-type]
        intent="two paragraphs framing the event",
        acceptance=AcceptanceCriteria(description="who/what/when covered"),
    )


def _sources() -> list[Source]:
    return [
        Source(
            id="s1",
            url="https://reuters.com/a",
            publisher=Publisher(name="Reuters", tier="T1"),
            title="t",
            published_at="2026-03-19T12:00:00Z",
            fetched_at="2026-03-19T13:00:00Z",
            language="en",
            rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
            summary="Reuters reports on NVIDIA's GTC keynote.",
        )
    ]


def test_returns_system_and_user_messages():
    msgs = build_block_extract_messages(
        section=_section(),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="NVIDIA GTC 2026",
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"


def test_system_message_contains_spec_extraction_fragment():
    msgs = build_block_extract_messages(
        section=_section("paragraph"),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="t",
    )
    system = msgs[0]["content"]
    # The spec's fragment must be embedded.
    assert "paragraphs_md" in system


def test_user_message_includes_evidence_pool_and_intent():
    msgs = build_block_extract_messages(
        section=_section(),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="NVIDIA GTC 2026",
    )
    user = msgs[1]["content"]
    assert "NVIDIA GTC 2026" in user
    assert "s1" in user  # source id present in evidence block
    assert "two paragraphs framing the event" in user  # section intent
    assert "who/what/when covered" in user  # acceptance description


def test_each_block_kind_uses_its_own_fragment():
    """Sanity: changing block_kind changes the system message."""
    p_sys = build_block_extract_messages(
        section=_section("paragraph"),
        spec=get_spec("paragraph"),
        sources=_sources(),
        canonical_title="t",
    )[0]["content"]
    t_sys = build_block_extract_messages(
        section=_section("timeline"),
        spec=get_spec("timeline"),
        sources=_sources(),
        canonical_title="t",
    )[0]["content"]
    assert p_sys != t_sys
