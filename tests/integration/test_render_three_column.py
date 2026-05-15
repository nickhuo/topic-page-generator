from generator.pipeline.render import render_html
from tests.fixtures import canned_event_page


def test_layout_has_three_column_landmarks():
    page = canned_event_page()
    html = render_html(page)
    assert 'aria-label="Sections"' in html  # left TOC <nav>
    assert 'aria-label="Reference"' in html  # right <aside>
    assert '<main id="main"' in html
    assert 'class="page-grid"' in html


def test_layout_no_longer_uses_old_nav_chrome():
    page = canned_event_page()
    html = render_html(page)
    assert 'class="needs-nav"' not in html  # old chrome/nav.html marker


def test_toc_js_is_injected():
    page = canned_event_page()
    html = render_html(page)
    assert "IntersectionObserver" in html  # the TOC script body


def test_hero_renders_last_updated_chip():
    page = canned_event_page()
    html = render_html(page)
    assert 'class="hero__updated"' in html


def test_section_renders_category_chip_when_set():
    page = canned_event_page()
    new_plans = [p.model_copy(update={"category": "fact"}) for p in page.need_plans]
    page = page.model_copy(update={"need_plans": new_plans})
    html = render_html(page)
    assert 'class="need-section__chip need-section__chip--fact"' in html


def _page_with_reactions():
    from generator.schema import (
        NeedCurationPlan,
        ReactionItem,
        ReactionsData,
        ReactionsModule,
    )
    from tests.fixtures import canned_event_page, conf

    page = canned_event_page()
    reactions = ReactionsModule(
        module_id="m_react",
        serves_needs=["world_reaction"],
        citations=[],
        confidence=conf(),
        slot="primary",
        artifact="ReactionStream",
        inclusion_reason="high",
        data=ReactionsData(
            items=[
                ReactionItem(
                    author=f"A{i}",
                    author_role=f"role{i}",
                    quote=f"quote {i}",
                    sentiment="positive",
                    source_id="s1",
                    stakeholder_tier="stakeholder" if i < 2 else "third_party",
                )
                for i in range(5)
            ]
        ),
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


def test_reactions_render_as_quote_cards_limited_to_four():
    html = render_html(_page_with_reactions())
    assert 'class="quote-card"' in html
    assert html.count('class="quote-card"') == 4


def test_reactions_stakeholders_rendered_before_third_party():
    html = render_html(_page_with_reactions())
    # A0 is a stakeholder; A3 is a third_party that survives the 4-card cap.
    pos_a0 = html.find("A0")
    pos_a3 = html.find("A3")
    assert 0 <= pos_a0 < pos_a3


def test_sources_render_in_card_not_ol_in_footer():
    page = canned_event_page()
    html = render_html(page)
    footer_start = html.find("<footer")
    footer_block = html[footer_start:]
    assert "<ol" not in footer_block
    assert 'class="sources-card"' in html


def test_event_page_accepts_optional_wikipedia_card():
    from generator.schema import WikipediaCardData

    base = canned_event_page()
    assert base.wikipedia_card is None  # field exists, defaults to None
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


def test_reference_rail_renders_milestones_only():
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
