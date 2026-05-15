"""Shared test fixture builders for EventPage instances."""

from __future__ import annotations

from generator.blocks.schema import (
    NewsCard,
    NewsfeedBlockData,
    ParagraphBlockData,
)
from generator.schema import (
    Citation,
    EventLayout,
    EventMeta,
    EventPage,
    EventSubject,
    Publisher,
    RenderedSection,
    Source,
    SourceRights,
)


def _src(i: int) -> Source:
    return Source(
        id=f"s{i}",
        url=f"https://example.com/a{i}",
        publisher=Publisher(name=f"Pub{i}", tier="T0"),
        title=f"Title {i}",
        published_at="2026-05-14T00:00:00Z",
        fetched_at="2026-05-14T00:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=999, can_paraphrase=True),
    )


def canned_event_page() -> EventPage:
    """Minimal EventPage using the editorial sections render path."""
    now = "2026-05-14T00:00:00Z"
    sections = [
        RenderedSection(
            section_id="overview",
            block_kind="paragraph",
            block_data=ParagraphBlockData(
                paragraphs_md=["Sample event happened today."],
            ),
        ),
        RenderedSection(
            section_id="media_coverage",
            block_kind="newsfeed",
            block_data=NewsfeedBlockData(
                cards=[
                    NewsCard(
                        url="https://example.com/a1",
                        title="Coverage Title",
                        publisher="Pub1",
                        tier="T0",
                    )
                ]
            ),
        ),
    ]
    return EventPage(
        page_id="p_test",
        input_sentence="Sample event happened today.",
        generated_at=now,
        subject=EventSubject(
            title="Sample Event",
            subtitle="A sample event used in tests.",
            entities=["Sample Event"],
            when=now,
        ),
        layout=EventLayout(preset_id="reference", overrides=None),
        sources=[_src(1)],
        editorial_sections=sections,
        meta=EventMeta(
            last_updated=now,
            editor_approved=True,
            editor_id="test",
            pipeline_trace_id="t1",
        ),
    )


def source(
    sid: str = "s1", url: str = "https://example.com/a", tier: str = "T0"
) -> Source:
    return Source(
        id=sid,
        url=url,
        publisher=Publisher(name=f"pub-{sid}", tier=tier),
        title=f"Title {sid}",
        published_at="2026-05-01T00:00:00Z",
        fetched_at="2026-05-01T00:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=999, can_paraphrase=True),
    )


# --- Task 8 additions ---------------------------------------------------------


def make_full_event_page(preset_id: str = "reference"):
    """Synthesise an EventPage with editorial sections and valid citations."""
    sources_ = [
        source("s1", "https://example.com/a", "T0"),
        source("s2", "https://example.com/b", "T1"),
        source("s3", "https://example.com/c", "T2"),
    ]

    sections = [
        RenderedSection(
            section_id="overview",
            block_kind="paragraph",
            block_data=ParagraphBlockData(
                paragraphs_md=[
                    "Big Event summary.",
                    "More context.",
                ],
                citations=[
                    Citation(source_id="s1", claim_text="Big Event summary."),
                    Citation(source_id="s2", claim_text="More context."),
                ],
            ),
        ),
        RenderedSection(
            section_id="media_coverage",
            block_kind="newsfeed",
            block_data=NewsfeedBlockData(
                cards=[
                    NewsCard(
                        url="https://example.com/a",
                        title="Coverage A",
                        publisher="Pub1",
                        tier="T0",
                    ),
                    NewsCard(
                        url="https://example.com/b",
                        title="Coverage B",
                        publisher="Pub2",
                        tier="T1",
                    ),
                ]
            ),
        ),
    ]

    layout = EventLayout.model_construct(preset_id=preset_id)
    return EventPage(
        page_id="p1",
        input_sentence="Big event happened.",
        generated_at="2026-05-01T00:00:00Z",
        subject=EventSubject(
            title="Big Event",
            subtitle="A big event subtitle.",
            entities=["Big Event"],
        ),
        layout=layout,
        sources=sources_,
        editorial_sections=sections,
        meta=EventMeta(
            last_updated="2026-05-01T00:00:00Z",
            editor_approved=True,
            pipeline_trace_id="tr1",
        ),
    )
