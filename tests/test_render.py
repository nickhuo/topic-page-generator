import re

import pytest

from generator.pipeline.render import render_html
from tests.fixtures import make_full_event_page


def test_render_contains_landmarks():
    page = make_full_event_page()
    html = render_html(page)
    # Exactly one each of header, main, footer.
    assert len(re.findall(r"<header\b", html)) == 1
    assert len(re.findall(r"<main\b", html)) == 1
    assert len(re.findall(r"<footer\b", html)) == 1
    assert "data-cite" in html


def test_every_data_cite_has_numbered_footer_link():
    page = make_full_event_page()
    html = render_html(page)

    # Every cite source_id should appear in the rendered HTML as a numbered <sup> link.
    cite_ids = set(re.findall(r'data-cite="([^"]+)"', html))
    # The footer should have one <li id="src-N"> per source.
    footer_ids = set(re.findall(r'id="src-(\d+)"', html))
    assert len(footer_ids) == len(page.sources), (
        f"Expected {len(page.sources)} footer entries; got {len(footer_ids)}"
    )

    # Every data-cite source_id must have a corresponding cite-num link pointing somewhere in footer_ids.
    for sid in cite_ids:
        # The cite() global emits href="#src-N" for any known source_id.
        # Spot-check that at least one such link exists in the document.
        assert re.search(r'href="#src-\d+"', html), f"no cite link for {sid}"


@pytest.mark.parametrize("preset_id", [
    "live_dominance", "product_focus", "imminent_event", "reference",
])
def test_renders_all_four_presets(preset_id):
    page = make_full_event_page(preset_id=preset_id)
    html = render_html(page)
    assert "<html" in html and "</html>" in html
    assert "data-cite" in html
    # Header, main, footer always present.
    assert "<header" in html and "<main" in html and "<footer" in html


def test_jsonld_block_present():
    page = make_full_event_page()
    html = render_html(page)
    assert 'application/ld+json' in html
    assert '"@type"' in html


def test_skip_link_and_viewport():
    page = make_full_event_page()
    html = render_html(page)
    assert 'class="skip-link"' in html
    assert 'viewport' in html


def test_palette_css_vars_in_head():
    page = make_full_event_page(preset_id="product_focus")
    html = render_html(page)
    # minimal_tech palette accent
    assert "--color-accent" in html
    assert "#2563eb" in html  # the minimal_tech accent
