"""BlockSpec ABC — one per BlockKind. Owns extraction + render + eval contracts.

Each concrete spec declares the data shape it consumes, a prompt fragment
that explains that shape to the LLM, a render template path, and a check
that decides whether extracted data is worth rendering at all.

Section-specific intent and acceptance criteria are injected at runtime by
the planner — they are NOT baked into the spec.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar

from pydantic import BaseModel

from generator.schema import AcceptanceCriteria, BlockKind


class BlockSpec(ABC):
    kind: ClassVar[BlockKind]
    data_schema: ClassVar[type[BaseModel]]
    template_path: ClassVar[str]
    extraction_prompt_fragment: ClassVar[str]
    default_acceptance: ClassVar[AcceptanceCriteria]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Late import to avoid circular dependency with __init__.py.
        from generator.blocks.specs import _REGISTRY

        if "kind" in cls.__dict__:
            _REGISTRY[cls.kind] = cls

    @abstractmethod
    def is_minimum_viable(self, data: BaseModel) -> bool:
        """Return False to drop a section whose extracted data is too thin."""
