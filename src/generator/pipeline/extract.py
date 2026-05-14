"""Stage 5 — Module extraction. Stub returns hardcoded modules conforming to schema.

PR 2 fix: every citation's `source_id` now points at a real fetched source so
schema invariant #3 (every source_id referenced in a citation must exist in
EventPage.sources[]) holds. PR 4 will replace this with real LLM extraction.
"""
from __future__ import annotations

from generator.schema import (
    BackgroundData,
    BackgroundModule,
    BackgroundParagraph,
    Citation,
    ConfidenceSignals,
    HeroData,
    HeroModule,
    InfoboxData,
    InfoboxModule,
    InfoboxRow,
    ModuleConfidence,
    Source,
    SourceTier,
    TypedModule,
)

_OK_SIGNALS = ConfidenceSignals(
    source_count=2,
    publisher_count=2,
    highest_tier="T0",
    schema_passes=True,
    cross_source_agreement=1.0,
)


def _conf(overall: float = 0.9) -> ModuleConfidence:
    return ModuleConfidence(overall=overall, signals=_OK_SIGNALS)


_TIER_ORDER: dict[SourceTier, int] = {"T0": 0, "T1": 1, "T2": 2, "T3": 3}


def _pick(sources: list[Source], n: int) -> str:
    """Pick the n-th best available source id, falling back to the first.

    `sources` arrives sorted by the orchestrator (tier asc, recency desc),
    so index 0 is the highest-quality reference. We index defensively so
    short evidence pools still produce valid citations.
    """
    if not sources:
        # Degenerate path: produce a placeholder id. The page won't render
        # cleanly but this keeps the stub from raising. PR 4 replaces all of this.
        return "src_unknown"
    return sources[min(n, len(sources) - 1)].id


def run(sources: list[Source]) -> list[TypedModule]:
    primary = _pick(sources, 0)
    secondary = _pick(sources, 1)

    hero = HeroModule(
        module_id="mod_hero",
        serves_needs=["what_happened"],
        citations=[
            Citation(
                source_id=primary,
                excerpt="Introducing GPT-5.5 Instant",
                claim_text="GPT-5.5 Instant is the new default model in ChatGPT.",
            )
        ],
        confidence=_conf(),
        slot="hero",
        artifact="HeroBanner",
        artifact_alternatives=[],
        inclusion_reason="required",
        data=HeroData(
            title="GPT-5.5 Instant is now the default in ChatGPT",
            subtitle="OpenAI rolls out a faster, cheaper default model",
            summary="OpenAI made GPT-5.5 Instant the default ChatGPT model in May 2026.",
            image_alt="OpenAI logo",
            badge_label="Product Launch",
        ),
    )
    infobox = InfoboxModule(
        module_id="mod_infobox",
        serves_needs=["when_where", "who_involved"],
        citations=[
            Citation(source_id=primary, claim_text="Rolled out in May 2026 by OpenAI."),
        ],
        confidence=_conf(),
        slot="aside",
        artifact="Infobox",
        artifact_alternatives=[],
        inclusion_reason="required",
        data=InfoboxData(
            rows=[
                InfoboxRow(label="Vendor", value="OpenAI", source_id=primary),
                InfoboxRow(label="Release", value="May 2026", source_id=primary),
                InfoboxRow(label="Replaces", value="GPT-5.3 Instant", source_id=primary),
                InfoboxRow(label="Surface", value="ChatGPT default", source_id=primary),
                InfoboxRow(label="Pricing", value="Same tiers", source_id=secondary),
            ]
        ),
    )
    background = BackgroundModule(
        module_id="mod_background",
        serves_needs=["why_matters", "what_happened"],
        citations=[
            Citation(
                source_id=secondary,
                claim_text="The rollout follows months of incremental Instant-tier model releases.",
            )
        ],
        confidence=_conf(0.82),
        slot="primary",
        artifact="Prose",
        artifact_alternatives=[],
        inclusion_reason="high",
        data=BackgroundData(
            paragraphs=[
                BackgroundParagraph(
                    text=(
                        "GPT-5.5 Instant succeeds GPT-5.3 Instant as the default "
                        "ChatGPT model. OpenAI says it is faster and cheaper "
                        "while preserving the existing tool-use feature set."
                    ),
                    citations=[
                        Citation(
                            source_id=primary,
                            claim_text="GPT-5.5 Instant is faster and cheaper than its predecessor.",
                        )
                    ],
                )
            ]
        ),
    )
    return [hero, infobox, background]
