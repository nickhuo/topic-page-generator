"""Module ABC contract: schema, prompt, artifact, render gate, confidence."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import ClassVar, TypeVar
from pydantic import BaseModel, ConfigDict

from generator.schema import (
    AestheticPlanOutput,
    ConfidenceFlag,
    ConfidenceSignals,
    EventSubject,
    ModuleConfidence,
    NeedId,
    NeedPlanOutput,
    Source,
    SourceTier,
)


class PlanContext(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)
    subject: EventSubject
    need_plan: NeedPlanOutput
    aesthetic: AestheticPlanOutput


_DataT = TypeVar("_DataT", bound=BaseModel)


class Module(ABC):
    kind: ClassVar[str]
    serves_needs: ClassVar[list[NeedId]]
    allowed_artifacts: ClassVar[list[str]]
    data_schema: ClassVar[type[BaseModel]]
    extraction_prompt_template: ClassVar[str]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        from generator.modules import MODULE_REGISTRY

        if hasattr(cls, "kind"):
            MODULE_REGISTRY[cls.kind] = cls

    def default_artifact(self, ctx: "PlanContext", data: BaseModel) -> str:
        """Pick the canonical artifact name for this module kind.

        Kept for the `EventPage.modules[*].artifact` field; not used for
        template routing anymore (blocks layer replaced that). Modules can
        still override if they want context-sensitive variants.
        """
        return self.allowed_artifacts[0]

    @abstractmethod
    def should_render(self, data: BaseModel | None) -> bool: ...

    def confidence(
        self, data: BaseModel, sources_used: list[Source]
    ) -> ModuleConfidence:
        return compute_default_confidence(sources_used, data)


_TIER_RANK: dict[SourceTier, int] = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


def compute_default_confidence(
    sources_used: list[Source],
    data: BaseModel,
    *,
    contested_fields: list[str] | None = None,
) -> ModuleConfidence:
    publishers = {s.publisher.name for s in sources_used}
    highest_tier: SourceTier = min(
        (s.publisher.tier for s in sources_used),
        key=lambda t: _TIER_RANK[t],
        default="T3",
    )
    flags: list[ConfidenceFlag] = []
    if len(publishers) < 2:
        flags.append("single_source")
    if highest_tier not in ("T0", "T1"):
        flags.append("low_tier_only")
    if contested_fields:
        flags.append("contested_fact")
    overall = max(0.3, min(1.0, 0.9 - 0.15 * len(flags)))
    signals = ConfidenceSignals(
        source_count=len(sources_used),
        publisher_count=len(publishers),
        highest_tier=highest_tier,
        schema_passes=True,
        cross_source_agreement=1.0 if not contested_fields else 0.6,
    )
    return ModuleConfidence(overall=overall, signals=signals, flags=flags)
