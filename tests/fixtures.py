"""Shared test fixture builders for EventPage instances."""

from __future__ import annotations

from generator.blocks.schema import (
    NewsCard,
    NewsfeedBlockData,
    ParagraphBlockData,
)
from generator.schema import (
    BackgroundData,
    BackgroundModule,
    BackgroundParagraph,
    Citation,
    ConfidenceSignals,
    EventLayout,
    EventMeta,
    EventPage,
    EventSubject,
    HeroData,
    HeroModule,
    InfoboxData,
    InfoboxModule,
    InfoboxRow,
    MediaCoverageData,
    MediaCoverageItem,
    MediaCoverageModule,
    ModuleConfidence,
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
            entities=["Sample Event"],
            when=now,
        ),
        modules=[],
        layout=EventLayout(preset_id="reference", overrides=None),
        sources=[_src(1)],
        needs_coverage={},
        uncovered_needs=[],
        need_plans=[],
        editorial_sections=sections,
        meta=EventMeta(
            last_updated=now,
            editor_approved=True,
            editor_id="test",
            pipeline_trace_id="t1",
        ),
    )


def conf() -> ModuleConfidence:
    return ModuleConfidence(
        overall=0.9,
        signals=ConfidenceSignals(
            source_count=2,
            publisher_count=2,
            highest_tier="T0",
            schema_passes=True,
            cross_source_agreement=1.0,
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


def hero_module(slot: str = "hero") -> HeroModule:
    return HeroModule(
        module_id="m_hero",
        serves_needs=["what_happened"],
        citations=[],
        confidence=conf(),
        slot=slot,
        artifact="HeroBanner",
        inclusion_reason="required",
        data=HeroData(title="A title", summary="A summary.", image_alt=""),
    )


def infobox_module(slot: str = "aside", rows: int = 3) -> InfoboxModule:
    return InfoboxModule(
        module_id="m_info",
        serves_needs=["when_where"],
        citations=[],
        confidence=conf(),
        slot=slot,
        artifact="Infobox",
        inclusion_reason="required",
        data=InfoboxData(
            rows=[
                InfoboxRow(label=f"L{i}", value=f"V{i}", source_id="s1")
                for i in range(rows)
            ]
        ),
    )


def media_coverage_module(slot: str = "aside") -> MediaCoverageModule:
    # MediaCoverageModule.should_render requires len(items) >= 3; supply 3 items
    # so the module passes the render gate and we can test the aux whitelist demotion.
    items = [
        MediaCoverageItem(
            headline=f"H{i}",
            publisher="P",
            publisher_tier="T1",
            published_at="2026-05-01T00:00:00Z",
            url=f"https://example.com/x{i}",
            snippet="snip",
            source_id="s1",
        )
        for i in range(3)
    ]
    return MediaCoverageModule(
        module_id="m_media",
        serves_needs=["world_reaction"],
        citations=[],
        confidence=conf(),
        slot=slot,
        artifact="CoverageList",
        inclusion_reason="medium",
        data=MediaCoverageData(
            items=items,
            grouping_strategy="flat",
        ),
    )


def background_module(empty: bool = False) -> BackgroundModule:
    # BackgroundModule.should_render requires all paragraphs to have non-empty citations.
    # When empty=True, we supply a paragraph with citations=[] so should_render returns False.
    # BackgroundData requires min_length=1 paragraph, so we cannot pass an empty list.
    if empty:
        paragraphs = [BackgroundParagraph(text="Some text.", citations=[])]
    else:
        from generator.schema import Citation

        paragraphs = [
            BackgroundParagraph(
                text="Some text.",
                citations=[Citation(source_id="s1", claim_text="fact")],
            )
        ]
    return BackgroundModule(
        module_id="m_bg",
        serves_needs=["why_matters"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="Prose",
        inclusion_reason="low",
        data=BackgroundData(paragraphs=paragraphs),
    )


def event_page(
    *,
    modules,
    preset_id: str = "reference",
    sources_=None,
) -> EventPage:
    if sources_ is None:
        sources_ = [source("s1"), source("s2", "https://example.com/b", "T1")]
    # Use model_construct to bypass Literal validation when testing unknown preset IDs.
    layout = EventLayout.model_construct(preset_id=preset_id)
    return EventPage(
        page_id="p1",
        input_sentence="x",
        generated_at="2026-05-01T00:00:00Z",
        subject=EventSubject(
            title="E",
            entities=["E"],
        ),
        modules=modules,
        layout=layout,
        sources=sources_,
        needs_coverage={
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
        },
        uncovered_needs=[],
        meta=EventMeta(
            last_updated="2026-05-01T00:00:00Z",
            editor_approved=True,
            pipeline_trace_id="tr1",
        ),
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
            entities=["Big Event"],
        ),
        modules=[],
        layout=layout,
        sources=sources_,
        needs_coverage={},
        uncovered_needs=[],
        editorial_sections=sections,
        meta=EventMeta(
            last_updated="2026-05-01T00:00:00Z",
            editor_approved=True,
            pipeline_trace_id="tr1",
        ),
    )
