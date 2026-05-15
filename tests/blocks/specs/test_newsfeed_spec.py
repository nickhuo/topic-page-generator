from generator.blocks.schema import NewsfeedBlockData, NewsCard
from generator.blocks.specs.newsfeed import NewsfeedBlockSpec


def _card(url="https://e.example/a") -> NewsCard:
    return NewsCard(url=url, title="t", publisher="P", tier="T1")


def test_newsfeed_spec_metadata():
    spec = NewsfeedBlockSpec()
    assert spec.kind == "newsfeed"
    assert spec.template_path == "blocks/newsfeed.html"


def test_newsfeed_minimum_viable_needs_two_cards():
    spec = NewsfeedBlockSpec()
    one = NewsfeedBlockData(cards=[_card()])
    two = NewsfeedBlockData(
        cards=[_card("https://e.example/a"), _card("https://e.example/b")]
    )
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(two) is True
