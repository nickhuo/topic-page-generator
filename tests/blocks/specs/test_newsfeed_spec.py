from generator.blocks.schema import NewsfeedBlockData, NewsCard
from generator.blocks.specs.newsfeed import NewsfeedBlockSpec, NEWSFEED_MAX_CARDS


def _card(
    url: str = "https://e.example/a",
    *,
    thumbnail: str | None = "https://img.example/x.jpg",
    published_at: str | None = "2026-05-15T00:00:00Z",
) -> NewsCard:
    return NewsCard(
        url=url,
        title="t",
        publisher="P",
        tier="T1",
        thumbnail_url=thumbnail,
        published_at=published_at,
    )


def test_newsfeed_spec_metadata():
    spec = NewsfeedBlockSpec()
    assert spec.kind == "newsfeed"
    assert spec.template_path == "blocks/newsfeed.html"


def test_minimum_viable_requires_three_image_cards():
    spec = NewsfeedBlockSpec()
    two = NewsfeedBlockData(
        cards=[_card("https://e.example/a"), _card("https://e.example/b")]
    )
    three = NewsfeedBlockData(
        cards=[
            _card("https://e.example/a"),
            _card("https://e.example/b"),
            _card("https://e.example/c"),
        ]
    )
    assert spec.is_minimum_viable(two) is False
    assert spec.is_minimum_viable(three) is True


def test_postprocess_drops_cards_without_thumbnail():
    spec = NewsfeedBlockSpec()
    data = NewsfeedBlockData(
        cards=[
            _card("https://e.example/a", thumbnail=None),
            _card("https://e.example/b"),
            _card("https://e.example/c"),
        ]
    )
    out = spec.postprocess(data)
    urls = [str(c.url) for c in out.cards]
    assert "https://e.example/a" not in urls
    assert "https://e.example/b" in urls
    assert "https://e.example/c" in urls


def test_postprocess_sorts_newest_first_and_caps_at_five():
    spec = NewsfeedBlockSpec()
    data = NewsfeedBlockData(
        cards=[
            _card("https://e.example/a", published_at="2026-05-01T00:00:00Z"),
            _card("https://e.example/b", published_at="2026-05-10T00:00:00Z"),
            _card("https://e.example/c", published_at="2026-05-15T00:00:00Z"),
            _card("https://e.example/d", published_at="2026-05-12T00:00:00Z"),
            _card("https://e.example/e", published_at="2026-05-05T00:00:00Z"),
            _card("https://e.example/f", published_at="2026-04-30T00:00:00Z"),
            _card("https://e.example/g", published_at="2026-05-13T00:00:00Z"),
        ]
    )
    out = spec.postprocess(data)
    assert len(out.cards) == NEWSFEED_MAX_CARDS
    dates = [c.published_at for c in out.cards]
    assert dates == sorted(dates, reverse=True)
    assert dates[0] == "2026-05-15T00:00:00Z"
