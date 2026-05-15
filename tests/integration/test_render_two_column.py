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
