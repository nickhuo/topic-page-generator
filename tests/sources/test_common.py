from generator.sources._common import build_source_id, host_of


def test_build_source_id_is_stable():
    assert build_source_id("https://example.com/a") == build_source_id(
        "https://example.com/a"
    )
    assert build_source_id("https://example.com/a").startswith("src_")
    assert len(build_source_id("https://example.com/a")) == 16  # "src_" + 12 hex chars


def test_build_source_id_differs_per_url():
    assert build_source_id("https://example.com/a") != build_source_id(
        "https://example.com/b"
    )


def test_host_of_strips_www():
    assert host_of("https://www.reuters.com/path") == "reuters.com"
    assert host_of("https://en.wikipedia.org/wiki/X") == "en.wikipedia.org"


def test_host_of_lowercases():
    assert host_of("https://Reuters.COM/x") == "reuters.com"
