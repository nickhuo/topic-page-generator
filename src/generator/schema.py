"""Pydantic v2 models — the runtime contract.

Source of truth: docs/schema.md. If anything diverges, schema.md wins and
this file is wrong.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


# ---------------------------------------------------------------------------
# Primitive aliases
# ---------------------------------------------------------------------------
ISO8601 = str  # TODO: tighten to datetime with serializer if downstream needs it
SourceId = str
PageId = str
TraceId = str


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
SourceTier = Literal["T0", "T1", "T2", "T3"]
Sentiment = Literal["positive", "neutral", "negative"]
Priority = Literal["required", "high", "medium", "low"]

ConfidenceFlag = Literal[
    "single_source",
    "low_tier_only",
    "contested_fact",
    "single_sentiment_perspective",
]

# Aesthetic enums (§6)
AestheticPresetId = Literal[
    "live_dominance", "product_focus", "imminent_event", "reference"
]
PaletteId = Literal[
    "festive_warm",
    "minimal_tech",
    "urgent_red",
    "urgent_light",
    "muted_solemn",
    "bold_sport",
    "neutral_news",
]
Density = Literal["compact", "standard", "sparse"]
TypographyWeight = Literal["tight", "standard", "loose"]
HeroMood = Literal[
    "solemn_portrait",
    "celebratory_kinetic",
    "minimalist_product",
    "urgent_breaking",
    "anticipatory_buildup",
    "factual_neutral",
    "data_focused",
    "monumental_static",
]
CopyRegister = Literal[
    "formal_official",
    "warm_engaged",
    "urgent_direct",
    "somber_reflective",
    "analytical_measured",
]


class _Frozen(BaseModel):
    model_config = ConfigDict(extra="forbid")


# ---------------------------------------------------------------------------
# §1 Foundation: Source, Citation
# ---------------------------------------------------------------------------
class Publisher(_Frozen):
    name: str
    tier: SourceTier
    logo_url: HttpUrl | None = None


class SourceRights(_Frozen):
    max_excerpt_words: int
    can_paraphrase: bool


class Source(_Frozen):
    id: SourceId
    url: HttpUrl
    publisher: Publisher
    title: str
    author: str | None = None
    published_at: ISO8601
    fetched_at: ISO8601
    language: str
    rights: SourceRights
    archive_url: HttpUrl | None = None
    # Editor-architecture: which SectionPlan.section_id values this source backs.
    serves_sections: list[str] = Field(default_factory=list)
    thumbnail_url: HttpUrl | None = None
    summary: str | None = None
    enriched_at: ISO8601 | None = None


class Citation(_Frozen):
    source_id: SourceId
    excerpt: str | None = None
    claim_text: str


class WikipediaCardData(_Frozen):
    """Reference rail card data fetched from the Wikipedia REST summary API."""

    title: str
    summary_text: str = Field(max_length=600)
    thumbnail_url: HttpUrl | None = None
    article_url: HttpUrl
    retrieved_at: ISO8601


class HeroImage(_Frozen):
    """Background image for the page chrome hero.

    Fetched once at pipeline start (via Brave Image Search). Decorative —
    pipeline must not fail if this is None.
    """

    image_url: HttpUrl
    alt_text: str | None = None
    source_url: HttpUrl | None = None
    publisher: str | None = None


# ---------------------------------------------------------------------------
# §3 Confidence signals (shared by sections)
# ---------------------------------------------------------------------------
class ConfidenceSignals(_Frozen):
    source_count: int
    publisher_count: int
    highest_tier: SourceTier
    schema_passes: bool
    cross_source_agreement: float = Field(ge=0.0, le=1.0)


class ModuleConfidence(_Frozen):
    overall: float = Field(ge=0.0, le=1.0)
    field_level: dict[str, float] = Field(default_factory=dict)
    signals: ConfidenceSignals
    flags: list[ConfidenceFlag] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# §6 LayoutConfig
# ---------------------------------------------------------------------------
class ContainerPadding(_Frozen):
    desktop: int
    mobile: int


class HeroLayout(_Frozen):
    placement: Literal["full_bleed", "in_main", "split", "none"]
    height_px: int
    mobile_height_px: int


class ColumnsLayout(_Frozen):
    count: Literal[1, 2, 3]
    ratios: list[float]
    gap_px: int


class AuxLayout(_Frozen):
    sticky_first_item: bool
    max_items: int
    max_height_pct_of_main: float = Field(ge=0.0, le=1.0)
    whitelist: list[str]


class MobileLayout(_Frozen):
    breakpoint_px: int
    aux_strategy: Literal["inline_after_hero", "sink_to_bottom", "interleave"]
    aux_priority_in_mobile: list[str]


class DesignTokens(_Frozen):
    palette: PaletteId
    density: Density
    typography_scale: TypographyWeight


class LayoutSignals(_Frozen):
    live_pill: bool
    sticky_top_strip: Literal["live", "breaking"] | None = None


class LayoutConfig(_Frozen):
    container_max_width: int
    container_padding: ContainerPadding
    hero: HeroLayout
    columns: ColumnsLayout
    aux: AuxLayout
    mobile: MobileLayout
    design_tokens: DesignTokens
    signals: LayoutSignals


# ---------------------------------------------------------------------------
# §2 Page root
# ---------------------------------------------------------------------------
class EventSubject(_Frozen):
    """Page-level identity, derived from the ground stage's EventFacts.

    `entities[0]` is the primary entity (the main subject of the page);
    additional entries are co-actors (e.g. ["Donald Trump", "China"] for
    "Trump visits China"). `when` and `where` are sourced from the
    supporting evidence, not from LLM parametric memory.
    """

    title: str
    subtitle: str = Field(min_length=1, max_length=240)
    entities: list[str] = Field(min_length=1)
    when: ISO8601 | None = None
    where: str | None = None


class EventLayout(_Frozen):
    preset_id: AestheticPresetId
    # TODO: schema.md says Partial<LayoutConfig>; modeled here as full optional
    # config. Tighten in PR 4 when overrides actually carry partial deltas.
    overrides: LayoutConfig | None = None


class EventMeta(_Frozen):
    last_updated: ISO8601
    editor_approved: bool
    editor_id: str | None = None
    pipeline_trace_id: TraceId


class EventPage(_Frozen):
    page_id: PageId
    input_sentence: str
    generated_at: ISO8601
    subject: EventSubject
    layout: EventLayout
    sources: list[Source]
    editorial_sections: list["RenderedSection"]
    # Optional Wikipedia reference card surfaced in the right rail. Filled
    # by the ground stage when a confident canonical title is available; the
    # render path no-ops cleanly when this is None.
    wikipedia_card: WikipediaCardData | None = None
    # Optional hero background image fetched via Brave Image Search. Decorative
    # — page renders cleanly when None.
    hero_image: HeroImage | None = None
    meta: EventMeta


# ---------------------------------------------------------------------------
# §4 Pipeline stage outputs
# ---------------------------------------------------------------------------
class EventFacts(_Frozen):
    """Grounded facts about the event, extracted from Tavily evidence.

    Produced by the ground stage's LLM call over real search results — every
    field traces back to one or more `supporting_sources`. `when` MUST come
    from a source's `published_at` or in-body date, never from parametric
    memory.
    """

    entities: list[str] = Field(min_length=1)
    what: str
    when: ISO8601 | None = None
    where: str | None = None
    why: str | None = None
    subtitle: str | None = Field(default=None, max_length=240)
    supporting_sources: list[SourceId] = Field(default_factory=list)


class GroundOutput(_Frozen):
    """Stage 1 output. Combines the "is this an unfolding hot event?" gate
    with grounded fact extraction in a single LLM call over Tavily evidence.

    When `is_hot_event=False`, `rejection_reason` explains why and `facts`
    is None. When True, `facts` and `canonical_title` are populated.
    """

    is_hot_event: bool
    rejection_reason: str | None = None
    facts: EventFacts | None = None
    canonical_title: str | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


# ---------------------------------------------------------------------------
# Editor-architecture section types
# ---------------------------------------------------------------------------
BlockKind = Literal[
    "paragraph",
    "timeline",
    "chart",
    "newsfeed",
    "factsheet",
    "map",
    "reactions",
    "gallery",
]

BackboneSectionId = Literal[
    "overview",
    "timeline",
    "background",
    "media_coverage",
]

SectionKind = Literal["backbone", "curated"]

Placement = Literal["main", "sidebar"]


class AcceptanceCriteria(_Frozen):
    """What the research loop must achieve before a section is considered done."""

    description: str
    min_sources: int = 1
    min_publishers: int = 1
    required_facets: list[str] = Field(default_factory=list)
    forbid_single_perspective: bool = False


class SectionPlan(_Frozen):
    """One section to render on the page — produced by the editorial planner.

    `section_id` is a BackboneSectionId literal when `kind="backbone"`, and a
    free-form snake_case string for curated sections (e.g. "people_relationships",
    "kpi_dashboard"). Validation is deferred to the planner stage.
    """

    section_id: str
    kind: SectionKind
    title: str
    rank: int = Field(ge=1, le=20)
    block_kind: BlockKind
    intent: str
    acceptance: AcceptanceCriteria
    placement: Placement = "main"


class SectionPlanOutput(_Frozen):
    """Combined output of backbone + curation planners."""

    sections: list[SectionPlan]


class ResearchEvalResult(_Frozen):
    """LLM judge output: is the section's evidence pool satisfactory?

    Used inside the per-section research loop. If `satisfied=False`, `gaps`
    must be non-empty (the LLM has to articulate what's missing) and
    `next_query_hint` is the LLM's best guess at what Tavily query would
    fill the gap.
    """

    satisfied: bool
    gaps: list[str] = Field(default_factory=list)
    next_query_hint: str | None = None

    @model_validator(mode="after")
    def _gaps_required_when_unsatisfied(self) -> ResearchEvalResult:
        if not self.satisfied and not self.gaps:
            raise ValueError(
                "ResearchEvalResult.satisfied=False requires at least one gap"
            )
        return self


class RenderedSection(_Frozen):
    """A fully extracted section, ready for the renderer.

    Replaces what TypedModule carried in the old architecture: block data,
    citations, source attribution, and the section's eval outcome. Confidence
    is computed at render time from `sources_used`, not stored here.
    """

    section_id: str
    block_kind: BlockKind
    block_data: Any  # validated as RenderBlock by _block_kind_matches_data below
    citations: list["Citation"] = Field(default_factory=list)
    sources_used: list["Source"] = Field(default_factory=list)
    eval_passed: bool = True
    eval_notes: str | None = None
    placement: Placement = "main"

    @model_validator(mode="after")
    def _block_kind_matches_data(self) -> "RenderedSection":
        data_kind = getattr(self.block_data, "kind", None)
        if data_kind is not None and data_kind != self.block_kind:
            raise ValueError(
                f"block_kind={self.block_kind} but block_data.kind={data_kind}"
            )
        return self


class ConsistencyIssue(_Frozen):
    severity: Literal["warning", "error"]
    module_kind: str
    field_path: str
    description: str
    recommended_action: Literal["regenerate", "remove", "manual_review"]


class ConsistencyCheckOutput(_Frozen):
    passes: bool
    issues: list[ConsistencyIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# §5 Trace and editor action log
# ---------------------------------------------------------------------------
class StageTokens(_Frozen):
    input: int
    output: int


class LLMCall(_Frozen):
    model: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    duration_ms: int


class StageTrace(_Frozen):
    stage: str
    started_at: ISO8601
    duration_ms: int
    model: str | None = None
    tokens: StageTokens | None = None
    cost_usd: float | None = None
    outcome: Literal["success", "fallback", "skipped", "error"]
    retry_count: int = 0
    error: str | None = None
    output_ref: str | None = None
    llm_calls: list[LLMCall] = Field(default_factory=list)


class EditorActionTarget(_Frozen):
    section_id: str | None = None
    field_path: str | None = None


EditorActionKind = Literal[
    "accept_section",
    "regenerate_section",
    "edit_section_field",
    "skip_section",
    "override_archetype",
    "override_preset",
    "approve_page",
    "reject_page",
    "save_draft",
]


class EditorAction(_Frozen):
    action_at: ISO8601
    actor: str
    action: EditorActionKind
    target: EditorActionTarget | None = None
    before: Any = None
    after: Any = None
    reason: str | None = None


class TraceApproval(_Frozen):
    actor: str
    approved_at: ISO8601 | None = None
    auto_mode: bool


class Trace(_Frozen):
    trace_id: TraceId
    page_id: PageId
    input_sentence: str
    started_at: ISO8601
    ended_at: ISO8601
    total_duration_ms: int
    total_cost_usd: float
    pipeline_trace: list[StageTrace]
    editor_actions: list[EditorAction] = Field(default_factory=list)
    final_outcome: Literal[
        "approved_published", "rejected", "draft_saved", "auto_approved"
    ]
    approval: TraceApproval
