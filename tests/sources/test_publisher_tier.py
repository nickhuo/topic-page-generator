from generator.sources.publisher_tier import tier_for


def test_t0_contextual_openai():
    assert tier_for("https://openai.com/blog/x", primary_entity="OpenAI") == "T0"
    assert (
        tier_for("https://openai.com/blog/x", primary_entity="GPT-5.5 by OpenAI")
        == "T0"
    )


def test_t0_only_when_entity_matches():
    # openai.com is T0 only when the event is about OpenAI; otherwise T3.
    assert (
        tier_for("https://openai.com/blog/x", primary_entity="FIFA World Cup") == "T3"
    )


def test_t0_case_insensitive():
    assert (
        tier_for("https://FIFA.com/news", primary_entity="fifa world cup 2026") == "T0"
    )


def test_t1_lookup():
    assert tier_for("https://www.reuters.com/article/x") == "T1"
    assert tier_for("https://apnews.com/x") == "T1"
    assert tier_for("https://www.bbc.co.uk/news/x") == "T1"


def test_t2_reference():
    assert tier_for("https://en.wikipedia.org/wiki/X") == "T2"
    assert tier_for("https://www.wikidata.org/entity/Q42") == "T2"


def test_t3_fallback():
    assert tier_for("https://random-blog.example/x") == "T3"


def test_no_entity_no_t0():
    # Without primary_entity we cannot verify primary-source relationship → never T0.
    assert tier_for("https://openai.com/blog/x") == "T3"
