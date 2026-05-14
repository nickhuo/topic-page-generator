# Data Schemas

> Type definitions for the topic page generator. Written in TypeScript-style for readability; will be implemented in Python as Pydantic models. Every schema here is the **source of truth** — pipeline stages and templates conform to these types.

## Contents

1. [Foundation: primitives, sources, citations](#1-foundation)
2. [Page root: `EventPage`](#2-page-root)
3. [Module base + 12 module kinds](#3-modules)
4. [Pipeline stage outputs](#4-pipeline-stage-outputs)
5. [Trace and editor action log](#5-trace-and-editor)
6. [Layout configuration and aesthetic presets](#6-layout)

---

## 1. Foundation

### Primitive aliases

```typescript
type ISO8601 = string;            // e.g. "2026-05-12T14:32:08Z"
type SourceId = string;            // system-internal source identifier
type ModuleId = string;            // unique within a page
type PageId = string;
type TraceId = string;
```

### Enumerations

```typescript
type SourceTier =
  | "T0"   // primary/official (event's own site, gov, corp IR)
  | "T1"   // independent tier-1 news (Reuters, AP, BBC, Bloomberg, NYT)
  | "T2"   // Wikipedia / Wikidata
  | "T3";  // other public web (regional, trade, blogs)

type TemporalPosture =
  | "live"     // happening now (Eurovision opening night)
  | "imminent" // scheduled within ~30 days (World Cup pre-kickoff)
  | "recent"   // happened within ~7 days (GPT-5.5 rolled out 7 days ago)
  | "past";    // happened >7 days ago

type Sentiment = "positive" | "neutral" | "negative";

type Priority = "required" | "high" | "medium" | "low";

type Slot = "hero" | "primary" | "aside" | "tail" | "footer";

type NeedId =
  | "what_happened"      // What is it / what happened
  | "when_where"         // When and where
  | "who_involved"       // Who is involved
  | "current_state"      // What's the current state
  | "why_matters"        // Why does it matter
  | "world_reaction"     // What's the world saying
  | "what_can_do"        // What can I do / engage with
  | "what_next";         // What comes next
```

The eight `NeedId` values are the closed set of reader information needs every event page must address. Every module declares which needs it serves; the page aggregates coverage and flags any uncovered need.

### `Source` — first-class entity

```typescript
type Source = {
  id: SourceId;
  url: string;
  publisher: {
    name: string;                    // "Reuters", "Eurovoix", "OpenAI"
    tier: SourceTier;
    logo_url?: string;
  };
  title: string;
  author?: string;
  published_at: ISO8601;
  fetched_at: ISO8601;
  language: string;                  // ISO 639-1, e.g. "en", "de"
  rights: {
    max_excerpt_words: number;       // 30 for T1–T3, unlimited for T0 primary sources
    can_paraphrase: boolean;         // true for T0 and T2 (reference); false for T1, T3
  };
  archive_url?: string;              // Wayback Machine link, optional
};
```

### `Citation` — every fact-bearing field carries one or more

```typescript
type Citation = {
  source_id: SourceId;
  excerpt?: string;                  // verbatim, ≤ source.rights.max_excerpt_words
  claim_text: string;                // the claim this citation supports
};
```

---

## 2. Page Root

### `EventPage`

```typescript
type EventPage = {
  page_id: PageId;
  input_sentence: string;            // the original one-sentence input
  generated_at: ISO8601;

  subject: {
    primary_entity: string;          // "GPT-5.5 Instant", "Eurovision 2026"
    event_type_hint: string;         // soft tag, e.g. "product_launch"
    temporal_posture: TemporalPosture;
    time_anchor?: ISO8601;           // event date if event-bound
  };

  modules: TypedModule[];            // discriminated union, see §3

  layout: {
    preset_id: AestheticPresetId;
    overrides?: Partial<LayoutConfig>; // editor-set overrides
  };

  sources: Source[];                 // every source referenced on this page

  needs_coverage: Record<NeedId, ModuleId[]>;  // which modules serve each need
  uncovered_needs: NeedId[];                   // auto-computed; empty means full coverage

  meta: {
    last_updated: ISO8601;
    editor_approved: boolean;
    editor_id?: string;
    pipeline_trace_id: TraceId;      // pointer to the trace.json record
  };
};
```

The `needs_coverage` map is derived at render time from each module's `serves_needs[]` declaration. `uncovered_needs` is the set of `NeedId` values with empty arrays in `needs_coverage`. A page may publish with `uncovered_needs` non-empty (the editor decides), but the field is always rendered in the trace so the gap is visible.

---

## 3. Modules

### `BaseModuleFields` — shared by every module

```typescript
type BaseModuleFields = {
  module_id: ModuleId;
  serves_needs: NeedId[];            // which information needs this module addresses
  citations: Citation[];             // every module owns its citations
  confidence: ModuleConfidence;
  slot: Slot;
  artifact: string;                  // chosen artifact (e.g. "Timeline")
  artifact_alternatives: string[];   // other allowed artifacts (editor swap)
  inclusion_reason: Priority;
};

type ConfidenceFlag =
  | "single_source"          // <2 unique publishers
  | "low_tier_only"          // no T0/T1/T2 sources
  | "contested_fact";        // conflicting sources

type ModuleConfidence = {
  overall: number;                   // 0.0 – 1.0
  field_level: Record<string, number>;
  signals: {
    source_count: number;
    publisher_count: number;
    highest_tier: SourceTier;
    schema_passes: boolean;
    cross_source_agreement: number;  // 0–1, fraction of claims with multi-source backing
  };
  flags: ConfidenceFlag[];
};
```

### `TypedModule` — discriminated union

```typescript
type TypedModule =
  | HeroModule
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
  | BackgroundModule;
```

### Default need-to-module mapping

Each module's `serves_needs` is set by the module's contract at extraction time. The default mapping is below; per-event variation is allowed (e.g. a `KPINumbers` module for a casualty count also serves `current_state`).

| Need             | Default served by                                                    |
| ---------------- | -------------------------------------------------------------------- |
| `what_happened`  | `Hero`, `Background`                                                 |
| `when_where`     | `Infobox`, `Schedule`, `Countdown`                                   |
| `who_involved`   | `Infobox`, `OfficialStatements`, `Comparison`                        |
| `current_state`  | `KPINumbers`, `Schedule` (live items), `MediaCoverage` (most recent) |
| `why_matters`    | `Background`, `Comparison`, `KPINumbers`                             |
| `world_reaction` | `Reactions`, `MediaCoverage`                                         |
| `what_can_do`    | `WhereToWatch`                                                       |
| `what_next`      | `Countdown`, `Schedule` (future items)                               |

`how_known` is treated specially: it is considered satisfied whenever a module's `citations` array is non-empty. Every typed module satisfies this by schema invariant, so `how_known` is never in `uncovered_needs` for a validly rendered page.

### Module: `Hero`

```typescript
type HeroModule = BaseModuleFields & {
  kind: "hero";
  data: {
    title: string;                   // ≤80 chars
    subtitle?: string;               // ≤120 chars
    summary: string;                 // ≤140 chars, one sentence
    image_url?: string;
    image_alt: string;               // accessibility, required when image_url present
    badge_label?: string;            // "Product Launch", "Live Now", "Imminent"
  };
};
```

### Module: `Infobox`

```typescript
type InfoboxModule = BaseModuleFields & {
  kind: "infobox";
  data: {
    rows: Array<{
      label: string;                 // "Host city", "Release date"
      value: string | string[];
      source_id: SourceId;
    }>;                              // 5–9 rows recommended
  };
};
```

### Module: `Schedule`

```typescript
type ScheduleModule = BaseModuleFields & {
  kind: "schedule";
  data: {
    items: Array<{
      time_iso: ISO8601;
      label: string;                 // "Semi-final 1"
      location?: string;
      duration_min?: number;
      source_id: SourceId;
    }>;
    timezone: string;                // IANA tz, e.g. "Europe/Vienna"
  };
};
```

### Module: `Countdown`

```typescript
type CountdownModule = BaseModuleFields & {
  kind: "countdown";
  data: {
    target_at: ISO8601;
    label: string;                   // "Until kickoff at Estadio Azteca"
    source_id: SourceId;
  };
};
```

### Module: `KPINumbers`

```typescript
type KPINumbersModule = BaseModuleFields & {
  kind: "kpi_numbers";
  data: {
    tiles: Array<{
      value: string;                 // "52.5%", "37", "$1.2B"
      unit?: string;
      label: string;                 // "Fewer hallucinations"
      comparison?: string;           // "vs GPT-5.3 Instant"
      source_id: SourceId;
    }>;                              // 1–4 tiles
  };
};
```

### Module: `Comparison`

```typescript
type ComparisonModule = BaseModuleFields & {
  kind: "comparison";
  data: {
    subjects: Array<{                // 2–3 entities being compared
      name: string;                  // "GPT-5.5 Instant"
      label?: string;                // "current"
    }>;
    axes: Array<{
      label: string;                 // "Hallucination rate"
      cells: Array<{
        value: string;
        source_id: SourceId;
      }>;                            // length === subjects.length
    }>;
  };
};
```

### Module: `Changelog`

```typescript
type ChangelogModule = BaseModuleFields & {
  kind: "changelog";
  data: {
    version_label: string;           // "GPT-5.5 Instant"
    previous_version_label?: string; // "GPT-5.3 Instant"
    entries: Array<{
      label: string;                 // "Memory sources control"
      description: string;           // ≤80 words
      importance: "breaking" | "feature" | "minor";
      source_id: SourceId;
    }>;
  };
};
```

### Module: `Reactions`

```typescript
type ReactionsModule = BaseModuleFields & {
  kind: "reactions";
  data: {
    items: Array<{
      author: string;                // named individual
      author_role: string;           // "Tech journalist", "Developer"
      quote: string;                 // verbatim, ≤280 chars
      sentiment: Sentiment;
      source_id: SourceId;
    }>;                              // 5–15 items
    aggregate_sentiment?: {
      positive_count: number;
      neutral_count: number;
      negative_count: number;
    };
  };
};
```

### Module: `MediaCoverage`

```typescript
type MediaCoverageModule = BaseModuleFields & {
  kind: "media_coverage";
  data: {
    items: Array<{
      headline: string;
      publisher: string;
      publisher_tier: SourceTier;
      published_at: ISO8601;
      url: string;
      snippet: string;               // ≤30 words
      perspective?: "favorable" | "critical" | "neutral";
      sub_topic?: string;            // optional cluster label
      source_id: SourceId;
    }>;
    grouping_strategy:
      | "by_perspective"
      | "by_subtopic"
      | "by_time"
      | "flat";
  };
};
```

### Module: `OfficialStatements`

```typescript
type OfficialStatementsModule = BaseModuleFields & {
  kind: "official_statements";
  data: {
    items: Array<{
      author: string;                // named individual
      role: string;                  // "CEO"
      organization: string;          // "OpenAI"
      quote: string;                 // verbatim
      made_at: ISO8601;
      source_url: string;
      source_id: SourceId;
    }>;
  };
};
```

### Module: `WhereToWatch`

```typescript
type WhereToWatchModule = BaseModuleFields & {
  kind: "where_to_watch";
  data: {
    channels: Array<{
      type: "tv" | "streaming" | "in_person" | "radio" | "api" | "app";
      name: string;
      region?: string;               // ISO country code or region label
      url?: string;
      cost?: string;                 // "Free", "$25", "Subscribers only"
      source_id: SourceId;
    }>;
  };
};
```

### Module: `Background`

```typescript
type BackgroundModule = BaseModuleFields & {
  kind: "background";
  data: {
    paragraphs: Array<{
      text: string;                  // ≤200 words total across all paragraphs
      citations: Citation[];
    }>;                              // 1–2 paragraphs
  };
};
```

---

## 4. Pipeline Stage Outputs

### `TriageOutput` — Stage 1

```typescript
type TriageOutput = {
  is_event: boolean;
  primary_entity?: string;
  event_type_hint?: string;          // "product_launch", "live_cultural_event"
  temporal_posture?: TemporalPosture;
  time_anchor?: ISO8601;
  confidence: number;                // 0–1
  alternatives?: Array<{
    entity: string;
    event_type_hint: string;
    rationale: string;
  }>;
  reasoning: string;                 // short LLM rationale, for audit
};
```

### `DisambiguationOutput` — Stage 2

```typescript
type DisambiguationOutput = {
  resolved: boolean;
  chosen?: {
    entity: string;
    event_type_hint: string;
    time_anchor: ISO8601;
    supporting_sources: SourceId[];
  };
  unresolved_candidates?: Array<{
    entity: string;
    event_type_hint: string;
    rationale: string;
    supporting_sources: SourceId[];
  }>;
};
```

### `PlanOutput` — Stage 3a (deterministic)

```typescript
type PlanOutput = {
  archetype_hint: string;
  layout_preset_id: AestheticPresetId; // initial pick, may be revised at Stage 3b
  composition: Array<{
    module_kind: string;
    artifact: string;
    slot: Slot;
    priority: Priority;
    artifact_alternatives: string[];
  }>;
  source_strategy: {
    preferred_tiers: SourceTier[];
    time_range_days: number;
    min_publishers: number;
  };
};
```

### `AestheticPlanOutput` — Stage 3b (LLM)

```typescript
type AestheticPlanOutput = {
  preset_id: AestheticPresetId;
  preset_confidence: number;         // 0–1
  alternatives_considered: AestheticPresetId[];
  aesthetic_overrides: {
    palette?: PaletteId;
    density?: Density;
    typography_weight?: TypographyWeight;
    hero_mood?: HeroMood;
    copy_register?: CopyRegister;
  };
  reasoning: string;                 // short LLM rationale
};
```

### `ConsistencyCheckOutput` — Stage 6

```typescript
type ConsistencyCheckOutput = {
  passes: boolean;
  issues: Array<{
    severity: "warning" | "error";
    module_kind: string;
    field_path: string;              // e.g. "items[2].quote"
    description: string;
    recommended_action: "regenerate" | "remove" | "manual_review";
  }>;
};
```

---

## 5. Trace and Editor

### `LLMCall` — one entry per individual LLM round-trip

```typescript
type LLMCall = {
  model: string;                     // OpenRouter model identifier
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;                  // estimated from a per-model price table
  duration_ms: number;
};
```

### `StageTrace` — one entry per pipeline stage

```typescript
type StageTrace = {
  stage: string;                     // "triage", "extract:reactions"
  started_at: ISO8601;
  duration_ms: number;
  model?: string;                    // LLM model identifier if applicable
  tokens?: { input: number; output: number };
  cost_usd?: number;
  outcome: "success" | "fallback" | "skipped" | "error";
  retry_count: number;
  error?: string;
  output_ref?: string;               // hash or reference, not the full payload
  llm_calls: LLMCall[];              // one entry per LLM round-trip in this stage
                                     // (empty for deterministic stages)
};
```

### `EditorAction` — every editor decision captured

```typescript
type EditorAction = {
  action_at: ISO8601;
  actor: string;                     // "cli_user@local" or named editor
  action:
    | "accept_module"
    | "regenerate_module"
    | "edit_module_field"
    | "skip_module"
    | "override_archetype"
    | "override_preset"
    | "approve_page"
    | "reject_page"
    | "save_draft";
  target?: {
    module_kind?: string;
    field_path?: string;
  };
  before?: unknown;                  // for edits
  after?: unknown;
  reason?: string;                   // "single_source", or user-typed
};
```

### `Trace` — top-level record per page generation

```typescript
type Trace = {
  trace_id: TraceId;
  page_id: PageId;
  input_sentence: string;
  started_at: ISO8601;
  ended_at: ISO8601;
  total_duration_ms: number;
  total_cost_usd: number;

  pipeline_trace: StageTrace[];
  editor_actions: EditorAction[];

  final_outcome:
    | "approved_published"
    | "rejected"
    | "draft_saved"
    | "auto_approved";

  approval: {
    actor: string;
    approved_at?: ISO8601;
    auto_mode: boolean;
  };
};
```

---

## 6. Layout

### Aesthetic enums

```typescript
type AestheticPresetId =
  | "live_dominance"      // live events (Eurovision opening night)
  | "product_focus"       // product/tech launches (GPT-5.5)
  | "imminent_event"      // scheduled future (World Cup pre-kickoff)
  | "reference";          // default fallback / generic entity page

type PaletteId =
  | "festive_warm"
  | "minimal_tech"
  | "urgent_red"
  | "muted_solemn"
  | "bold_sport"
  | "neutral_news";

type Density = "compact" | "standard" | "sparse";

type TypographyWeight = "tight" | "standard" | "loose";

type HeroMood =
  | "solemn_portrait"
  | "celebratory_kinetic"
  | "minimalist_product"
  | "urgent_breaking"
  | "anticipatory_buildup"
  | "factual_neutral"
  | "data_focused"
  | "monumental_static";

type CopyRegister =
  | "formal_official"
  | "warm_engaged"
  | "urgent_direct"
  | "somber_reflective"
  | "analytical_measured";
```

### `LayoutConfig`

```typescript
type LayoutConfig = {
  container_max_width: number;       // px, e.g. 1180
  container_padding: {
    desktop: number;                 // px, e.g. 24
    mobile: number;                  // px, e.g. 16
  };

  hero: {
    placement: "full_bleed" | "in_main" | "split" | "none";
    height_px: number;
    mobile_height_px: number;
  };

  columns: {
    count: 1 | 2 | 3;
    ratios: number[];                // e.g. [0.65, 0.35]
    gap_px: number;
  };

  aux: {
    sticky_first_item: boolean;
    max_items: number;
    max_height_pct_of_main: number;  // 0–1
    whitelist: string[];             // module kinds permitted in aux slot
  };

  mobile: {
    breakpoint_px: number;           // e.g. 768
    aux_strategy: "inline_after_hero" | "sink_to_bottom" | "interleave";
    aux_priority_in_mobile: string[]; // module kinds, ordered
  };

  design_tokens: {
    palette: PaletteId;
    density: Density;
    typography_scale: TypographyWeight;
  };

  signals: {
    live_pill: boolean;
    countdown_in_hero: boolean;
    sticky_top_strip: "live" | "breaking" | null;
  };
};
```

### Preset library (~5 entries; named parameter sets, not types)

Defined at runtime in `src/layout/presets.py`. Each preset is a complete `LayoutConfig` instance. Editor or LLM can override any field per page.

---

## Schema invariants (must always hold)

1. **Every fact-bearing field has at least one citation.** Schema validation rejects any module whose typed data fields lack `source_id` or `citations`.
2. **`module.confidence.signals.schema_passes` must be `true` to render.** Any module that fails schema validation is dropped to empty state, never partial-rendered.
3. **Every `source_id` referenced in a citation must exist in `EventPage.sources[]`.** Orphan citations are validation errors.
4. **`EventPage.modules[]` is the only source of page content.** Layout never reads outside this array.
5. **Editor actions are append-only.** `EditorAction[]` is never edited or reordered after writing.
