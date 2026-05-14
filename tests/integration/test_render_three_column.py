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
