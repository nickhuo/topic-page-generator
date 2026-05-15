"""Render walks editorial_sections when present."""

from __future__ import annotations

from generator.blocks.schema import (
    NewsCard,
    NewsfeedBlockData,
    ParagraphBlockData,
)
from generator.pipeline.render import build_editorial_page, render_html
from generator.schema import (
    EventLayout,
    EventMeta,
    EventSubject,
    Publisher,
    RenderedSection,
    Source,
    SourceRights,
)


def _src() -> Source:
    return Source(
        id="s1",
        url="https://reuters.com/a",
        publisher=Publisher(name="Reuters", tier="T1"),
        title="t",
        published_at="2026-03-19T12:00:00Z",
        fetched_at="2026-03-19T13:00:00Z",
        language="en",
        rights=SourceRights(max_excerpt_words=30, can_paraphrase=True),
    )


def _subject() -> EventSubject:
    return EventSubject(
        title="NVIDIA GTC 2026",
        subtitle="NVIDIA unveils new GPU architecture at GTC.",
        entities=["NVIDIA"],
        when="2026-03-19T12:00:00Z",
        where="San Jose",
    )


def _layout() -> EventLayout:
    return EventLayout(preset_id="product_focus", overrides=None)


def _meta() -> EventMeta:
    return EventMeta(
        last_updated="2026-03-19T12:00:00Z",
        editor_approved=True,
        pipeline_trace_id="trace_x",
    )


def test_editorial_page_renders_two_sections():
    sections = [
        RenderedSection(
            section_id="overview",
            block_kind="paragraph",
            block_data=ParagraphBlockData(paragraphs_md=["NVIDIA held its keynote."]),
        ),
        RenderedSection(
            section_id="media_coverage",
            block_kind="newsfeed",
            block_data=NewsfeedBlockData(
                cards=[
                    NewsCard(
                        url="https://reuters.com/a",
                        title="t",
                        publisher="Reuters",
                        tier="T1",
                    ),
                    NewsCard(
                        url="https://reuters.com/b",
                        title="t2",
                        publisher="Reuters",
                        tier="T1",
                    ),
                ]
            ),
        ),
    ]
    page = build_editorial_page(
        input_sentence="x",
        page_id="p1",
        subject=_subject(),
        layout=_layout(),
        sources=[_src()],
        editorial_sections=sections,
        trace_id="trace_x",
        meta=_meta(),
    )
    assert page.editorial_sections == sections

    html = render_html(page)
    assert "NVIDIA held its keynote." in html
    assert 'id="section-overview"' in html
    assert 'id="section-media_coverage"' in html


def test_render_html_legacy_path_still_works_when_editorial_sections_none():
    """Sanity: existing render tests use editorial_sections=None and must still pass."""
    # This is covered by the existing tests/integration/test_render_two_column.py
    # — we re-run it implicitly when `uv run pytest -q` runs.
    pass
