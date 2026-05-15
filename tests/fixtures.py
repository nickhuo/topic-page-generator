"""Shared test fixture builders for EventPage instances."""

from __future__ import annotations

from generator.schema import (
    BackgroundData,
    BackgroundModule,
    BackgroundParagraph,
    ChangelogData,
    ChangelogEntry,
    ChangelogModule,
    Citation,
    ComparisonAxis,
    ComparisonCell,
    ComparisonData,
    ComparisonModule,
    ComparisonSubject,
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
    KPINumbersData,
    KPINumbersModule,
    KPITile,
    MediaCoverageData,
    MediaCoverageItem,
    MediaCoverageModule,
    ModuleConfidence,
    OfficialStatementItem,
    OfficialStatementsData,
    OfficialStatementsModule,
    Publisher,
    ReactionItem,
    ReactionsData,
    ReactionsModule,
    ScheduleData,
    ScheduleItem,
    ScheduleModule,
    Source,
    SourceRights,
    WhereToWatchChannel,
    WhereToWatchData,
    WhereToWatchModule,
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
    """Minimal EventPage with one hero module and one activated need plan."""
    now = "2026-05-14T00:00:00Z"
    hero = HeroModule(
        module_id="m_hero",
        serves_needs=["what_happened"],
        citations=[],
        confidence=conf(),
        slot="hero",
        artifact="HeroBanner",
        inclusion_reason="required",
        data=HeroData(
            title="Sample Event",
            subtitle="A subtitle",
            summary="One-sentence summary of the event.",
            image_alt="",
            badge_label="LIVE",
        ),
    )
    info = InfoboxModule(
        module_id="m_info",
        serves_needs=["when_where"],
        citations=[],
        confidence=conf(),
        slot="aside",
        artifact="Infobox",
        inclusion_reason="required",
        data=InfoboxData(
            rows=[InfoboxRow(label="When", value="Today", source_id="s1")]
        ),
    )
    from generator.schema import NeedCurationPlan

    plan = NeedCurationPlan(
        need_id="what_happened",
        activated=True,
        rank=1,
        section_title="What happened",
        rationale="Establish the core facts.",
        assigned_modules=["hero", "infobox"],
    )
    return EventPage(
        page_id="p_test",
        input_sentence="Sample event happened today.",
        generated_at=now,
        subject=EventSubject(
            title="Sample Event",
            entities=["Sample Event"],
            when=now,
        ),
        modules=[hero, info],
        layout=EventLayout(preset_id="reference", overrides=None),
        sources=[_src(1)],
        needs_coverage={"what_happened": ["m_hero"]},
        uncovered_needs=[],
        need_plans=[plan],
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
    """Synthesise an EventPage with all 12 module kinds and valid data."""
    sources_ = [
        source("s1", "https://example.com/a", "T0"),
        source("s2", "https://example.com/b", "T1"),
        source("s3", "https://example.com/c", "T2"),
    ]

    hero = hero_module()
    hero = hero.model_copy(
        update={"data": HeroData(title="Big Event", summary="Summary.", image_alt="")}
    )

    info = infobox_module(slot="aside", rows=4)

    sched = ScheduleModule(
        module_id="m_sched",
        serves_needs=["when_where"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="Timeline",
        inclusion_reason="high",
        data=ScheduleData(
            items=[
                ScheduleItem(
                    time_iso="2026-06-11T18:00:00Z",
                    label="Opening match",
                    source_id="s1",
                ),
                ScheduleItem(
                    time_iso="2026-06-12T18:00:00Z",
                    label="Second match",
                    source_id="s2",
                ),
            ],
            timezone="UTC",
        ),
    )

    kpi = KPINumbersModule(
        module_id="m_kpi",
        serves_needs=["current_state"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="KPITiles",
        inclusion_reason="medium",
        data=KPINumbersData(
            tiles=[
                KPITile(value="52.5%", label="Fewer hallucinations", source_id="s1"),
                KPITile(value="37", label="New features", source_id="s2"),
            ],
        ),
    )

    cmp_ = ComparisonModule(
        module_id="m_cmp",
        serves_needs=["why_matters"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="ComparisonTable",
        inclusion_reason="medium",
        data=ComparisonData(
            subjects=[ComparisonSubject(name="A"), ComparisonSubject(name="B")],
            axes=[
                ComparisonAxis(
                    label="Speed",
                    cells=[
                        ComparisonCell(value="fast", source_id="s1"),
                        ComparisonCell(value="slow", source_id="s2"),
                    ],
                ),
            ],
        ),
    )

    changelog = ChangelogModule(
        module_id="m_cl",
        serves_needs=["what_happened"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="ChangelogList",
        inclusion_reason="high",
        data=ChangelogData(
            version_label="v2",
            entries=[
                ChangelogEntry(
                    label="New thing",
                    description="It does X.",
                    importance="feature",
                    source_id="s1",
                ),
                ChangelogEntry(
                    label="Big change",
                    description="Breaks Y.",
                    importance="breaking",
                    source_id="s2",
                ),
            ],
        ),
    )

    reactions = ReactionsModule(
        module_id="m_rx",
        serves_needs=["world_reaction"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="ReactionStream",
        inclusion_reason="high",
        data=ReactionsData(
            items=[
                ReactionItem(
                    author=f"Person {i}",
                    author_role="Analyst",
                    quote=f"Quote {i}.",
                    sentiment="positive",
                    source_id="s1",
                )
                for i in range(5)
            ],
        ),
    )

    coverage = media_coverage_module(slot="tail")

    official = OfficialStatementsModule(
        module_id="m_os",
        serves_needs=["who_involved"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="QuoteStack",
        inclusion_reason="medium",
        data=OfficialStatementsData(
            items=[
                OfficialStatementItem(
                    author="CEO",
                    role="CEO",
                    organization="OpenAI",
                    quote="We shipped it.",
                    made_at="2026-05-01T00:00:00Z",
                    source_url="https://example.com/a",
                    source_id="s1",
                ),
            ],
        ),
    )

    watch = WhereToWatchModule(
        module_id="m_w2w",
        serves_needs=["what_can_do"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="ChannelGrid",
        inclusion_reason="high",
        data=WhereToWatchData(
            channels=[
                WhereToWatchChannel(type="streaming", name="Streamr", source_id="s1"),
            ],
        ),
    )

    bg = BackgroundModule(
        module_id="m_bg",
        serves_needs=["why_matters"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="Prose",
        inclusion_reason="low",
        data=BackgroundData(
            paragraphs=[
                BackgroundParagraph(
                    text="Some background prose here.",
                    citations=[Citation(source_id="s1", claim_text="background claim")],
                )
            ],
        ),
    )

    page = event_page(
        modules=[
            hero,
            info,
            sched,
            kpi,
            cmp_,
            changelog,
            reactions,
            coverage,
            official,
            watch,
            bg,
        ],
        preset_id=preset_id,
        sources_=sources_,
    )
    return page
