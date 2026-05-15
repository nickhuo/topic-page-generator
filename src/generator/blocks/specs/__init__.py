"""BlockSpec registry. One spec per BlockKind, registered on import.

Importing this package eagerly imports each spec module so the
`_REGISTRY` is fully populated. Callers use `get_spec(kind)`.
"""

from __future__ import annotations

from generator.blocks.specs.base import BlockSpec
from generator.schema import BlockKind

_REGISTRY: dict[BlockKind, type[BlockSpec]] = {}

# Eagerly import each spec so __init_subclass__ registers it.
from generator.blocks.specs import paragraph as _paragraph  # noqa: E402, F401
from generator.blocks.specs import timeline as _timeline  # noqa: E402, F401
from generator.blocks.specs import chart as _chart  # noqa: E402, F401
from generator.blocks.specs import factsheet as _factsheet  # noqa: E402, F401
from generator.blocks.specs import newsfeed as _newsfeed  # noqa: E402, F401
from generator.blocks.specs import map as _map  # noqa: E402, F401
from generator.blocks.specs import reactions as _reactions  # noqa: E402, F401
from generator.blocks.specs import gallery as _gallery  # noqa: E402, F401


def get_spec(kind: BlockKind) -> type[BlockSpec]:
    """Return the BlockSpec subclass for the given kind. Raises KeyError if unknown."""
    return _REGISTRY[kind]


ALL_BLOCK_KINDS: tuple[BlockKind, ...] = tuple(_REGISTRY.keys())

__all__ = ["BlockSpec", "get_spec", "ALL_BLOCK_KINDS"]
