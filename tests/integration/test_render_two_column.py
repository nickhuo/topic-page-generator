from generator.pipeline.render import render_html
from tests.fixtures import canned_event_page


def test_layout_has_two_column_landmarks():
    page = canned_event_page()
    html = render_html(page)
    assert 'aria-label="Page sections"' in html  # horizontal sticky nav
    assert 'aria-label="Reference"' in html  # right <aside>
    assert '<main id="main"' in html
    assert 'class="page-grid"' in html


def test_layout_uses_horizontal_nav_not_legacy_chrome():
    page = canned_event_page()
    html = render_html(page)
    assert 'class="needs-nav"' not in html  # old chrome/nav.html marker
    assert 'class="nav"' in html  # v2 horizontal sticky chip nav


def test_toc_js_is_injected():
    page = canned_event_page()
    html = render_html(page)
    assert "IntersectionObserver" in html


def test_hero_renders_updated_time():
    page = canned_event_page()
    html = render_html(page)
    assert 'class="hero__time"' in html


def test_section_chip_uses_single_neutral_style():
    page = canned_event_page()
    new_plans = [p.model_copy(update={"category": "fact"}) for p in page.need_plans]
    page = page.model_copy(update={"need_plans": new_plans})
    html = render_html(page)
    # v2 collapses fact/opinion to a single chip style; no variant suffix in class.
    assert 'class="need-section__chip"' in html
    assert "need-section__chip--fact" not in html


def _page_with_reactions(sentiments: list[str] | None = None):
    from generator.schema import (
        NeedCurationPlan,
        ReactionItem,
        ReactionsData,
        ReactionsModule,
    )
    from tests.fixtures import canned_event_page, conf

    page = canned_event_page()
    if sentiments is None:
        sentiments = ["positive", "negative", "positive", "neutral", "negative"]
    items = []
    for i, s in enumerate(sentiments):
        items.append(
            ReactionItem(
                author=f"A{i}",
                author_role=f"role{i}",
                quote=f"quote {i}",
                sentiment=s,
                source_id="s1",
                stakeholder_tier="stakeholder" if i < 2 else "third_party",
            )
        )
    reactions = ReactionsModule(
        module_id="m_react",
        serves_needs=["world_reaction"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="ReactionStream",
        inclusion_reason="high",
        data=ReactionsData(items=items),
    )
    new_plan = NeedCurationPlan(
        need_id="world_reaction",
        activated=True,
        rank=2,
        section_title="Reactions",
        rationale="How people responded.",
        assigned_modules=["reactions"],
        render_overrides={"reactions": "reactions"},
        category="opinion",
    )
    return page.model_copy(
        update={
            "modules": list(page.modules) + [reactions],
            "need_plans": list(page.need_plans) + [new_plan],
        }
    )


def test_reactions_render_as_perspectives_cards_limited_to_four():
    html = render_html(_page_with_reactions())
    assert 'class="pv-item"' in html
    assert html.count('class="pv-item"') == 4


def test_reactions_perspectives_tabs_visible_when_multiple_sentiments():
    html = render_html(_page_with_reactions())
    # tab bar renders without the `hidden` attribute when ≥2 sentiment groups exist
    assert 'class="pv-tabs" role="tablist"' in html
    assert 'class="pv-tabs" role="tablist" hidden' not in html


def test_reactions_single_sentiment_collapses_to_flat_layout():
    html = render_html(_page_with_reactions(["positive"] * 5))
    assert "block--reactions-flat" in html
    assert 'class="pv-tabs" role="tablist" hidden' in html


def test_reactions_stakeholders_rendered_before_third_party():
    html = render_html(_page_with_reactions())
    pos_a0 = html.find("A0")
    pos_a3 = html.find("A3")
    assert 0 <= pos_a0 < pos_a3


def test_no_sources_card_in_footer():
    page = canned_event_page()
    html = render_html(page)
    # v2 removed the page-bottom sources card; citations stay inline only.
    assert 'class="sources-card"' not in html
    footer_start = html.find("<footer")
    footer_block = html[footer_start:]
    assert "<ol" not in footer_block


def test_event_page_accepts_optional_wikipedia_card():
    from generator.schema import WikipediaCardData

    base = canned_event_page()
    assert base.wikipedia_card is None
    page = base.model_copy(
        update={
            "wikipedia_card": WikipediaCardData(
                title="t",
                summary_text="s",
                article_url="https://en.wikipedia.org/wiki/t",
                retrieved_at="2026-05-14T00:00:00Z",
            )
        }
    )
    assert page.wikipedia_card is not None
    assert page.wikipedia_card.title == "t"


def test_wikipedia_card_renders_with_attribution():
    from generator.schema import WikipediaCardData

    page = canned_event_page().model_copy(
        update={
            "wikipedia_card": WikipediaCardData(
                title="Test Entity",
                summary_text="A short summary about Test Entity.",
                thumbnail_url="https://upload.wikimedia.org/x.jpg",
                article_url="https://en.wikipedia.org/wiki/Test_Entity",
                retrieved_at="2026-05-14T00:00:00Z",
            )
        }
    )
    html = render_html(page)
    assert "Wikipedia" in html
    assert "CC BY-SA" in html
    assert "Test Entity" in html
    assert "https://en.wikipedia.org/wiki/Test_Entity" in html


def test_wikipedia_card_absent_renders_nothing():
    page = canned_event_page()
    html = render_html(page)
    assert "from Wikipedia" not in html
    assert "CC BY-SA" not in html


def test_reference_sidebar_renders_milestones_only():
    from generator.schema import (
        ScheduleData,
        ScheduleItem,
        ScheduleModule,
    )
    from tests.fixtures import canned_event_page, conf

    page = canned_event_page()
    sched = ScheduleModule(
        module_id="m_sched",
        serves_needs=["when_where"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="Timeline",
        inclusion_reason="high",
        data=ScheduleData(
            timezone="UTC",
            items=[
                ScheduleItem(
                    time_iso="2026-05-14T09:00:00Z",
                    label="Kickoff",
                    location="Stadium",
                    is_milestone=True,
                    source_id="s1",
                ),
                ScheduleItem(
                    time_iso="2026-05-14T09:15:00Z",
                    label="Throw-in",
                    is_milestone=False,
                    source_id="s1",
                ),
            ],
        ),
    )
    page = page.model_copy(update={"modules": list(page.modules) + [sched]})
    html = render_html(page)
    assert "Kickoff" in html
    assert "Throw-in" not in html
    assert 'class="ref-timeline"' in html
