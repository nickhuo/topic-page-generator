from generator.blocks.schema import QuoteCard, ReactionsBlock
from generator.blocks.specs.reactions import ReactionsBlockSpec


def _card(sentiment="neutral") -> QuoteCard:
    return QuoteCard(
        author="A",
        author_role="role",
        quote="q",
        sentiment=sentiment,  # type: ignore[arg-type]
        source_id="s1",
    )


def test_reactions_spec_metadata():
    spec = ReactionsBlockSpec()
    assert spec.kind == "reactions"
    assert spec.template_path == "blocks/reactions.html"


def test_reactions_minimum_viable_needs_two_cards_and_two_sentiments():
    spec = ReactionsBlockSpec()
    one = ReactionsBlock(cards=[_card("positive")])
    same = ReactionsBlock(cards=[_card("positive"), _card("positive")])
    diverse = ReactionsBlock(cards=[_card("positive"), _card("negative")])
    assert spec.is_minimum_viable(one) is False
    assert spec.is_minimum_viable(same) is False
    assert spec.is_minimum_viable(diverse) is True
