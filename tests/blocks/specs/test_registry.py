import pytest

from generator.blocks.specs import ALL_BLOCK_KINDS, BlockSpec, get_spec


def test_registry_covers_all_seven_block_kinds():
    expected = {
        "paragraph",
        "timeline",
        "chart",
        "newsfeed",
        "factsheet",
        "map",
        "reactions",
    }
    assert set(ALL_BLOCK_KINDS) == expected


@pytest.mark.parametrize(
    "kind",
    ["paragraph", "timeline", "chart", "newsfeed", "factsheet", "map", "reactions"],
)
def test_get_spec_returns_subclass(kind):
    spec_cls = get_spec(kind)
    assert issubclass(spec_cls, BlockSpec)
    assert spec_cls.kind == kind


def test_get_spec_unknown_kind_raises():
    with pytest.raises(KeyError):
        get_spec("not_a_kind")  # type: ignore[arg-type]


def test_each_spec_has_required_classvars():
    for kind in ALL_BLOCK_KINDS:
        spec_cls = get_spec(kind)
        assert spec_cls.data_schema is not None
        assert spec_cls.template_path.startswith("blocks/")
        assert spec_cls.extraction_prompt_fragment.strip()
        assert spec_cls.default_acceptance.description
