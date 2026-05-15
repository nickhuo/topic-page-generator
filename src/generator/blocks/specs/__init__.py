"""BlockSpec registry. Per-kind specs live in sibling modules.

The registry is populated lazily by importing each spec module (which
registers itself via `BlockSpec.__init_subclass__`). Task 11 wires up
get_spec() and the eager-import of all specs.
"""

from __future__ import annotations

from generator.blocks.specs.base import BlockSpec
from generator.schema import BlockKind

_REGISTRY: dict[BlockKind, type[BlockSpec]] = {}

__all__ = ["BlockSpec", "_REGISTRY"]
