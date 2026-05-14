"""Shared test fixture builders for EventPage instances."""
from __future__ import annotations

from generator.schema import (
    BackgroundData,
    BackgroundModule,
    BackgroundParagraph,
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
    Source,
    SourceRights,
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


def source(sid: str = "s1", url: str = "https://example.com/a", tier: str = "T0") -> Source:
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
            rows=[InfoboxRow(label=f"L{i}", value=f"V{i}", source_id="s1") for i in range(rows)]
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
            primary_entity="E",
            event_type_hint="generic",
            temporal_posture="recent",
        ),
        modules=modules,
        layout=layout,
        sources=sources_,
        needs_coverage={
            n: []
            for n in [
                "what_happened", "when_where", "who_involved", "current_state",
                "why_matters", "world_reaction", "what_can_do", "what_next",
            ]
        },
        uncovered_needs=[],
        meta=EventMeta(
            last_updated="2026-05-01T00:00:00Z",
            editor_approved=True,
            pipeline_trace_id="tr1",
        ),
    )
