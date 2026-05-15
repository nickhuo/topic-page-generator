"""BlockSpec ABC contract test."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria


def test_blockspec_cannot_be_instantiated_directly():
    with pytest.raises(TypeError):
        BlockSpec()  # type: ignore[abstract]


def test_blockspec_subclass_must_declare_required_classvars():
    class Incomplete(BlockSpec):
        pass

    with pytest.raises(AttributeError):
        Incomplete.kind  # accessing missing ClassVar


def test_blockspec_subclass_with_classvars_instantiates():
    class _Dummy(BaseModel):
        text: str

    class _DummySpec(BlockSpec):
        kind = "paragraph"
        data_schema = _Dummy
        template_path = "blocks/paragraph.html"
        extraction_prompt_fragment = "fragment"
        default_acceptance = AcceptanceCriteria(description="d")

        def is_minimum_viable(self, data):
            return bool(data.text)

    spec = _DummySpec()
    assert spec.kind == "paragraph"
    assert spec.is_minimum_viable(_Dummy(text="x")) is True
    assert spec.is_minimum_viable(_Dummy(text="")) is False
