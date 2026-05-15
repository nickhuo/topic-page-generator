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
    from generator.blocks.specs import _REGISTRY

    class _Dummy(BaseModel):
        text: str

    # Save the existing registry entry so we can restore it after the test.
    _prior = _REGISTRY.get("paragraph")

    class _DummySpec(BlockSpec):
        kind = "paragraph"
        data_schema = _Dummy
        template_path = "blocks/paragraph.html"
        extraction_prompt_fragment = "fragment"
        default_acceptance = AcceptanceCriteria(description="d")

        def is_minimum_viable(self, data):
            return bool(data.text)

    try:
        spec = _DummySpec()
        assert spec.kind == "paragraph"
        assert spec.is_minimum_viable(_Dummy(text="x")) is True
        assert spec.is_minimum_viable(_Dummy(text="")) is False
    finally:
        # Restore the original spec so other tests see ParagraphBlockSpec.
        if _prior is not None:
            _REGISTRY["paragraph"] = _prior
        else:
            _REGISTRY.pop("paragraph", None)
