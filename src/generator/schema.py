"""Pydantic v2 models — the runtime contract.

Source of truth: docs/schema.md. If anything diverges, schema.md wins and
this file is wrong.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


# ---------------------------------------------------------------------------
# Primitive aliases
# ---------------------------------------------------------------------------
ISO8601 = str  # TODO: tighten to datetime with serializer if downstream needs it
SourceId = str
ModuleId = str
PageId = str
TraceId = str


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------
SourceTier = Literal["T0", "T1", "T2", "T3"]
TemporalPosture = Literal["live", "imminent", "recent", "past"]
Sentiment = Literal["positive", "neutral", "negative"]
Priority = Literal["required", "high", "medium", "low"]
Slot = Literal["hero", "primary", "aside", "tail", "footer"]
NeedId = Literal[
    "what_happened",
    "when_where",
    "who_involved",
    "current_state",
    "why_matters",
    "world_reaction",
    "what_can_do",
    "what_next",
]

ConfidenceFlag = Literal[
    "single_source",
    "low_tier_only",
    "contested_fact",
]

# Aesthetic enums (§6)
AestheticPresetId = Literal[
    "live_dominance", "product_focus", "imminent_event", "reference"
]
PaletteId = Literal[
    "festive_warm",
    "minimal_tech",
    "urgent_red",
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
    # Phase-1 needs-driven additions. Default-empty / None so existing code paths
    # keep working until plan.py + fetch.py are switched over.
    serves_needs: list[NeedId] = Field(default_factory=list)
    thumbnail_url: HttpUrl | None = None
    summary: str | None = None
    enriched_at: ISO8601 | None = None


class Citation(_Frozen):
    source_id: SourceId
    excerpt: str | None = None
    claim_text: str


# ---------------------------------------------------------------------------
# §3 Module base
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


class _BaseModule(_Frozen):
    """Shared fields for every typed module. `kind` is the union discriminator."""

    module_id: ModuleId
    serves_needs: list[NeedId]
    citations: list[Citation]
    confidence: ModuleConfidence
    slot: Slot
    artifact: str
    artifact_alternatives: list[str] = Field(default_factory=list)
    inclusion_reason: Priority


# ---------------------------------------------------------------------------
# §3 Module data payloads and the 12 module variants
# ---------------------------------------------------------------------------
class OverviewBullet(_Frozen):
    text: str = Field(min_length=1)
    source_id: SourceId

    @field_validator("text")
    @classmethod
    def _cap_words(cls, v: str) -> str:
        if len(v.split()) > 18:
            raise ValueError("overview bullet text must be <= 18 words")
        return v


class HeroData(_Frozen):
    title: str = Field(max_length=80)
    subtitle: str | None = Field(default=None, max_length=120)
    summary: str = Field(max_length=140)
    image_url: HttpUrl | None = None
    image_alt: str  # TODO: enforce non-empty only when image_url is set
    badge_label: str | None = None
    overview_bullets: list[OverviewBullet] | None = Field(
        default=None, min_length=3, max_length=4
    )


class HeroModule(_BaseModule):
    kind: Literal["hero"] = "hero"
    data: HeroData


class InfoboxRow(_Frozen):
    label: str
    value: str | list[str]
    source_id: SourceId


class InfoboxData(_Frozen):
    rows: list[InfoboxRow]  # 5–9 recommended, not enforced


class InfoboxModule(_BaseModule):
    kind: Literal["infobox"] = "infobox"
    data: InfoboxData


class ScheduleItem(_Frozen):
    time_iso: ISO8601
    label: str
    location: str | None = None
    duration_min: int | None = None
    source_id: SourceId


class ScheduleData(_Frozen):
    items: list[ScheduleItem]
    timezone: str


class ScheduleModule(_BaseModule):
    kind: Literal["schedule"] = "schedule"
    data: ScheduleData


class CountdownData(_Frozen):
    target_at: ISO8601
    label: str
    source_id: SourceId


class CountdownModule(_BaseModule):
    kind: Literal["countdown"] = "countdown"
    data: CountdownData


class KPITile(_Frozen):
    value: str
    unit: str | None = None
    label: str
    comparison: str | None = None
    source_id: SourceId


class KPINumbersData(_Frozen):
    tiles: list[KPITile] = Field(min_length=1, max_length=4)


class KPINumbersModule(_BaseModule):
    kind: Literal["kpi_numbers"] = "kpi_numbers"
    data: KPINumbersData


class ComparisonSubject(_Frozen):
    name: str
    label: str | None = None


class ComparisonCell(_Frozen):
    value: str
    source_id: SourceId


class ComparisonAxis(_Frozen):
    label: str
    cells: list[
        ComparisonCell
    ]  # length must equal subjects length (enforced at extract)


class ComparisonData(_Frozen):
    subjects: list[ComparisonSubject] = Field(min_length=2, max_length=3)
    axes: list[ComparisonAxis]


class ComparisonModule(_BaseModule):
    kind: Literal["comparison"] = "comparison"
    data: ComparisonData


class ChangelogEntry(_Frozen):
    label: str
    description: str  # ≤80 words; enforced at extract
    importance: Literal["breaking", "feature", "minor"]
    source_id: SourceId


class ChangelogData(_Frozen):
    version_label: str
    previous_version_label: str | None = None
    entries: list[ChangelogEntry]


class ChangelogModule(_BaseModule):
    kind: Literal["changelog"] = "changelog"
    data: ChangelogData


class ReactionItem(_Frozen):
    author: str
    author_role: str
    quote: str = Field(max_length=280)
    sentiment: Sentiment
    source_id: SourceId
    stakeholder_tier: Literal["stakeholder", "adjacent", "third_party"] | None = None
    author_image_url: HttpUrl | None = None


class ReactionAggregate(_Frozen):
    positive_count: int
    neutral_count: int
    negative_count: int


class ReactionsData(_Frozen):
    items: list[ReactionItem] = Field(min_length=5, max_length=15)
    aggregate_sentiment: ReactionAggregate | None = None


class ReactionsModule(_BaseModule):
    kind: Literal["reactions"] = "reactions"
    data: ReactionsData


class MediaCoverageItem(_Frozen):
    headline: str
    publisher: str
    publisher_tier: SourceTier
    published_at: ISO8601
    url: HttpUrl
    snippet: str  # ≤30 words; enforced at extract
    perspective: Literal["favorable", "critical", "neutral"] | None = None
    sub_topic: str | None = None
    source_id: SourceId


class MediaCoverageData(_Frozen):
    items: list[MediaCoverageItem]
    grouping_strategy: Literal["by_perspective", "by_subtopic", "by_time", "flat"]


class MediaCoverageModule(_BaseModule):
    kind: Literal["media_coverage"] = "media_coverage"
    data: MediaCoverageData


class OfficialStatementItem(_Frozen):
    author: str
    role: str
    organization: str
    quote: str
    made_at: ISO8601
    source_url: HttpUrl
    source_id: SourceId


class OfficialStatementsData(_Frozen):
    items: list[OfficialStatementItem]


class OfficialStatementsModule(_BaseModule):
    kind: Literal["official_statements"] = "official_statements"
    data: OfficialStatementsData


class WhereToWatchChannel(_Frozen):
    type: Literal["tv", "streaming", "in_person", "radio", "api", "app"]
    name: str
    region: str | None = None
    url: HttpUrl | None = None
    cost: str | None = None
    source_id: SourceId


class WhereToWatchData(_Frozen):
    channels: list[WhereToWatchChannel]


class WhereToWatchModule(_BaseModule):
    kind: Literal["where_to_watch"] = "where_to_watch"
    data: WhereToWatchData


class BackgroundParagraph(_Frozen):
    text: str
    citations: list[Citation]


class BackgroundData(_Frozen):
    paragraphs: list[BackgroundParagraph] = Field(min_length=1, max_length=2)


class BackgroundModule(_BaseModule):
    kind: Literal["background"] = "background"
    data: BackgroundData


TypedModule = Annotated[
    HeroModule
    | InfoboxModule
    | ScheduleModule
    | CountdownModule
    | KPINumbersModule
    | ComparisonModule
    | ChangelogModule
    | ReactionsModule
    | MediaCoverageModule
    | OfficialStatementsModule
    | WhereToWatchModule
    | BackgroundModule,
    Field(discriminator="kind"),
]


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
    countdown_in_hero: bool
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
    primary_entity: str
    event_type_hint: str
    temporal_posture: TemporalPosture
    time_anchor: ISO8601 | None = None


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
    modules: list[TypedModule]
    layout: EventLayout
    sources: list[Source]
    needs_coverage: dict[NeedId, list[ModuleId]]
    uncovered_needs: list[NeedId]
    # The needs curation plan that produced this page (Phase 1 cutover).
    # Optional during migration so older fixtures still round-trip; once all
    # outputs are produced by the new plan stage, mark required.
    need_plans: list["NeedCurationPlan"] = Field(default_factory=list)
    meta: EventMeta


# ---------------------------------------------------------------------------
# §4 Pipeline stage outputs
# ---------------------------------------------------------------------------
class TriageAlternative(_Frozen):
    entity: str
    event_type_hint: str
    rationale: str


class TriageOutput(_Frozen):
    is_event: bool
    primary_entity: str | None = None
    event_type_hint: str | None = None
    temporal_posture: TemporalPosture | None = None
    time_anchor: ISO8601 | None = None
    confidence: float = Field(ge=0.0, le=1.0)
    alternatives: list[TriageAlternative] = Field(default_factory=list)
    reasoning: str


class DisambiguationChosen(_Frozen):
    entity: str
    event_type_hint: str
    time_anchor: ISO8601
    supporting_sources: list[SourceId]


class DisambiguationCandidate(_Frozen):
    entity: str
    event_type_hint: str
    rationale: str
    supporting_sources: list[SourceId]


class DisambiguationOutput(_Frozen):
    resolved: bool
    chosen: DisambiguationChosen | None = None
    unresolved_candidates: list[DisambiguationCandidate] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Phase-1 needs-driven plan types — the only plan contract.
# ---------------------------------------------------------------------------
BlockKind = Literal[
    "paragraph", "timeline", "chart", "newsfeed", "factsheet", "map", "reactions"
]

FetchAngle = Literal["news", "commentary", "official", "explainer"]


class FetchQuery(_Frozen):
    """A single Tavily-bound search the plan stage emits for a particular need."""

    query: str
    time_range_days: int | None = None
    angle: FetchAngle | None = None
    notes: str | None = None


class TierQuota(_Frozen):
    """Minimum number of sources required per publisher tier on a need."""

    t0: int = 0
    t1: int = 0
    t2: int = 0


class NeedCurationPlan(_Frozen):
    """Plan-stage instructions for one reader need.

    All 8 needs always appear in PlanOutput.need_plans; `activated=False` means
    the LLM (or editor) decided this need has no substance for this event and
    it should not be surfaced on the page.
    """

    need_id: NeedId
    activated: bool
    rank: int = Field(ge=1, le=8)
    section_title: str
    rationale: str
    fetch_queries: list[FetchQuery] = Field(default_factory=list)
    assigned_modules: list[str] = Field(default_factory=list)
    render_overrides: dict[str, BlockKind] = Field(default_factory=dict)
    publisher_quota: TierQuota = Field(default_factory=TierQuota)
    category: Literal["fact", "opinion"] | None = None
    opinion_subtag: str | None = None


class NeedPlanOutput(_Frozen):
    """Output of the new needs-driven plan stage (Phase 1 cutover target).

    Distinct from legacy PlanOutput so both can coexist during migration.
    """

    need_plans: list[NeedCurationPlan]
    layout_preset_id: AestheticPresetId  # carries over the deterministic preset hint


class AestheticOverrides(_Frozen):
    palette: PaletteId | None = None
    density: Density | None = None
    typography_weight: TypographyWeight | None = None
    hero_mood: HeroMood | None = None
    copy_register: CopyRegister | None = None


class AestheticPlanOutput(_Frozen):
    preset_id: AestheticPresetId
    preset_confidence: float = Field(ge=0.0, le=1.0)
    alternatives_considered: list[AestheticPresetId] = Field(default_factory=list)
    aesthetic_overrides: AestheticOverrides
    reasoning: str


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
    module_kind: str | None = None
    field_path: str | None = None


EditorActionKind = Literal[
    "accept_module",
    "regenerate_module",
    "edit_module_field",
    "skip_module",
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
