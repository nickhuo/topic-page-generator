# Data Schemas

> Source of truth for the runtime contract. Written in TypeScript-style for
> readability; implemented in Python as Pydantic v2 models in
> `src/generator/schema.py` (page + pipeline types) and
> `src/generator/blocks/schema.py` (render blocks). If anything diverges,
> **this document wins** and the code is wrong.

## Contents

1. [Foundation: primitives, sources, citations](#1-foundation)
2. [Page root: `EventPage`](#2-page-root)
3. [Sections and render blocks](#3-sections-and-render-blocks)
4. [Pipeline stage outputs](#4-pipeline-stage-outputs)
5. [Trace and editor action log](#5-trace-and-editor)
6. [Layout configuration and aesthetic presets](#6-layout)

---

## 1. Foundation

### Primitive aliases

```typescript
type ISO8601 = string;            // e.g. "2026-05-12T14:32:08Z"
type SourceId = string;            // system-internal source identifier
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

type Sentiment = "positive" | "neutral" | "negative";

type Priority = "required" | "high" | "medium" | "low";

type ConfidenceFlag =
  | "single_source"                    // <2 unique publishers
  | "low_tier_only"                    // no T0/T1/T2 sources
  | "contested_fact"                   // conflicting sources
  | "single_sentiment_perspective";    // reactions block lacks viewpoint mix
```

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

  // Editor-architecture bookkeeping
  serves_sections: string[];         // SectionPlan.section_id values this source backs
  thumbnail_url?: string;            // enrichment: og:image / page thumb
  summary?: string;                  // enrichment: short snippet for newsfeed cards
  enriched_at?: ISO8601;
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

### `WikipediaCardData` — reference rail card

Fetched once from the Wikipedia REST summary API at the ground stage when a
confident `canonical_title` is available. Decorative — the renderer no-ops
cleanly when absent.

```typescript
type WikipediaCardData = {
  title: string;
  summary_text: string;              // ≤600 chars
  thumbnail_url?: string;
  article_url: string;
  retrieved_at: ISO8601;
};
```

### `HeroImage` — page chrome background

Fetched once at pipeline start (Brave Image Search). Decorative — pipeline must
not fail if this is `null`.

```typescript
type HeroImage = {
  image_url: string;
  alt_text?: string;
  source_url?: string;
  publisher?: string;
};
```

### `ConfidenceSignals` / `ModuleConfidence`

Confidence is computed at render time from a section's `sources_used`. The
shape is retained for trace + future surfacing:

```typescript
type ConfidenceSignals = {
  source_count: number;
  publisher_count: number;
  highest_tier: SourceTier;
  schema_passes: boolean;
  cross_source_agreement: number;    // 0–1, fraction of claims with multi-source backing
};

type ModuleConfidence = {
  overall: number;                   // 0.0 – 1.0
  field_level: Record<string, number>;
  signals: ConfidenceSignals;
  flags: ConfidenceFlag[];
};
```

---

## 2. Page Root

### `EventPage`

```typescript
type EventPage = {
  page_id: PageId;
  input_sentence: string;            // original one-sentence input
  generated_at: ISO8601;

  subject: EventSubject;
  layout: EventLayout;
  sources: Source[];                 // every source referenced on this page
  editorial_sections: RenderedSection[];  // ordered, ready for the renderer

  wikipedia_card?: WikipediaCardData;     // optional right-rail reference card
  hero_image?: HeroImage;                 // optional chrome background

  meta: {
    last_updated: ISO8601;
    editor_approved: boolean;
    editor_id?: string;
    pipeline_trace_id: TraceId;      // pointer to the trace.json record
  };
};
```

### `EventSubject`

Page-level identity, derived from the ground stage's `EventFacts`. `entities[0]`
is the primary entity (main subject); additional entries are co-actors
(e.g. `["Donald Trump", "China"]` for "Trump visits China"). `when` and `where`
are sourced from supporting evidence, never from LLM parametric memory.

```typescript
type EventSubject = {
  title: string;                     // canonical page title from the ground stage
  subtitle: string;                  // 1–240 chars
  entities: string[];                // min 1; entities[0] is primary
  when?: ISO8601;
  where?: string;
};
```

### `EventLayout`

```typescript
type EventLayout = {
  preset_id: AestheticPresetId;
  overrides?: LayoutConfig;          // editor / LLM overrides (full config; partial deltas TBD)
};
```

---

## 3. Sections and Render Blocks

The editor architecture replaces the old "12 typed modules" with a two-level
contract:

- **`SectionPlan`** — the editorial planner's spec: what section to render,
  what block kind, what success looks like (`AcceptanceCriteria`).
- **`RenderedSection`** — the extracted output: a `RenderBlock` plus citations,
  attributed sources, and eval outcome.
- **`RenderBlock`** — a discriminated union (by `kind`) defining the actual
  payload the template consumes.

### `BlockKind` enumeration

```typescript
type BlockKind =
  | "paragraph"
  | "timeline"        // sidebar-only — backbone planner emits exclusively
  | "chart"
  | "newsfeed"
  | "reactions"
  | "gallery"
  | "latest_news"
  | "people";
```

### `BackboneSectionId` — the always-on backbone

Four deterministic sections pinned by `backbone_planner.py`:

```typescript
type BackboneSectionId =
  | "overview"
  | "timeline"
  | "media_coverage"
  | "latest_news";
```

Curated sections (`kind: "curated"`) use free-form snake_case ids
(e.g. `"people_relationships"`, `"kpi_dashboard"`).

### `SectionKind` / `Placement`

```typescript
type SectionKind = "backbone" | "curated";
type Placement   = "main" | "sidebar";
```

### `SectionPlan`

```typescript
type SectionPlan = {
  section_id: string;                // BackboneSectionId literal when kind="backbone"
  kind: SectionKind;
  title: string;
  rank: number;                      // 1–20
  block_kind: BlockKind;
  intent: string;                    // short editorial intent statement
  acceptance: AcceptanceCriteria;
  placement: Placement;              // default "main"
};

type AcceptanceCriteria = {
  description: string;
  min_sources: number;               // default 1
  min_publishers: number;            // default 1
  required_facets: string[];         // free-form tags the research loop must hit
  forbid_single_perspective: boolean; // default false
};

type SectionPlanOutput = {
  sections: SectionPlan[];           // backbone + curation combined
};
```

### `RenderedSection`

```typescript
type RenderedSection = {
  section_id: string;
  block_kind: BlockKind;
  block_data: RenderBlock;           // discriminated by `kind`; must match block_kind
  citations: Citation[];
  sources_used: Source[];
  eval_passed: boolean;              // default true
  eval_notes?: string;
  placement: Placement;              // default "main"
};
```

Schema invariant: `block_data.kind === block_kind` (validated by
`_block_kind_matches_data`).

### `RenderBlock` — discriminated union

```typescript
type RenderBlock =
  | ParagraphBlockData
  | TimelineBlockData
  | ChartBlockData
  | NewsfeedBlockData
  | ReactionsBlock
  | GalleryBlockData
  | LatestNewsBlockData
  | PeopleBlockData;
```

#### Shared block primitives

```typescript
type PullQuote = {
  quote: string;
  attribution?: string;
  source_id?: SourceId;
};

type NewsCard = {
  url: string;
  title: string;
  publisher: string;
  tier: SourceTier;
  published_at?: ISO8601;
  thumbnail_url?: string;
  summary?: string;
  source_id?: SourceId;
};

type TimelineEntry = {
  title: string;
  time?: string;                     // free-form: ISO8601 / "Jun 11" / "Quarter Finals"
  location?: string;
  description?: string;
  importance: "breaking" | "feature" | "minor" | "normal";  // default "normal"
  temporal_phase: "past" | "present" | "future";            // default "past"
  source_id?: SourceId;
};

type ChartSeries = { label: string; values: number[]; unit?: string };

type ChartStat = {
  value: string;
  unit?: string;
  label: string;
  comparison?: string;
  source_id?: SourceId;
};

type ComparisonRow   = { axis: string; cells: string[] };  // len == subjects.length
type ComparisonTable = { subjects: string[]; rows: ComparisonRow[] };

type QuoteCard = {
  author: string;
  author_role: string;
  quote: string;
  sentiment: Sentiment;
  stakeholder_tier?: "stakeholder" | "adjacent" | "third_party";
  author_image_url?: string;
  source_id: SourceId;
  // When article_url is present the whole card links there (replaces inline [N]).
  article_title?: string;
  article_url?: string;
  publisher?: string;
  publisher_logo_url?: string;
};

type PersonCard = {
  name: string;                      // 1–80
  role: string;                      // 1–120
  bio:  string;                      // 1–260
  image_url?: string;
  image_source: "wikipedia" | "wikidata" | "brave" | "none";  // default "none"
  image_credit_url?: string;
  profile_url?: string;
  source_ids: SourceId[];
};

type GalleryItem = {
  image_url: string;
  caption: string;                   // 1–240
  alt_text?: string;                 // ≤160
  source_url?: string;
};
```

#### Block variants

```typescript
type ParagraphBlockData = {
  kind: "paragraph";
  style: "prose" | "bullets";        // default "prose"
  paragraphs_md: string[];           // min 1
  // paragraph_sources[i] grounds paragraphs_md[i]; empty/shorter falls back to
  // the block's `citations` aggregated into a per-paragraph cite-cluster.
  paragraph_sources: SourceId[][];
  pull_quotes: PullQuote[];
  citations: Citation[];
};

type TimelineBlockData = {
  kind: "timeline";                  // sidebar-only, backbone-only
  entries: TimelineEntry[];          // min 1
  timezone?: string;
};

type ChartBlockData = {
  kind: "chart";
  chart_type: "bar" | "stat" | "compare_table";
  series?: ChartSeries[];            // used when chart_type === "bar"
  stats?: ChartStat[];               // used when chart_type === "stat"
  table?: ComparisonTable;           // used when chart_type === "compare_table"
  title?: string;
};

type NewsfeedBlockData = {
  kind: "newsfeed";
  cards: NewsCard[];                 // min 1
  variant: "news" | "channels" | "quotes";  // default "news"
  grouping: "by_perspective" | "by_subtopic" | "by_time" | "flat";  // default "flat"
};

type ReactionsBlock = {
  kind: "reactions";
  cards: QuoteCard[];                // max 4
};

type GalleryBlockData = {
  kind: "gallery";
  items: GalleryItem[];              // 1–12
  citations: Citation[];
};

type LatestNewsBlockData = {
  kind: "latest_news";               // vertical stack of landscape news cards
  cards: NewsCard[];                 // 1–8
};

type PeopleBlockData = {
  kind: "people";
  cards: PersonCard[];               // 2–6
};
```

> **Timeline placement rule.** `timeline` blocks are emitted exclusively by the
> backbone planner with `placement: "sidebar"`. The curation planner must
> never propose a `timeline` section.

---

## 4. Pipeline Stage Outputs

### `EventFacts` — grounded facts

Produced by the ground stage's LLM call over real Tavily evidence. Every field
traces back to one or more `supporting_sources`; `when` must come from a
source's `published_at` or in-body date, never from parametric memory.

```typescript
type EventFacts = {
  entities: string[];                // min 1, in order of centrality
  what: string;                      // one-sentence event description
  when?: ISO8601;
  where?: string;
  why?: string;
  subtitle?: string;                 // ≤240 chars; renders under the page title
  supporting_sources: SourceId[];
};
```

### `GroundOutput` — Stage 1

Combines the gate ("is this an unfolding hot event?") with grounded fact
extraction in a single LLM call.

```typescript
type GroundOutput = {
  is_hot_event: boolean;
  rejection_reason?: string;         // set when is_hot_event=false
  facts?: EventFacts;                // set when is_hot_event=true
  canonical_title?: string;          // human-readable page title
  confidence: number;                // 0–1
  reasoning: string;                 // short LLM rationale, for audit
};
```

When `is_hot_event=false` the CLI short-circuits and exits with code 5.

### `ResearchEvalResult` — per-section research-loop judge

Used inside the per-section research loop. When `satisfied=false`, `gaps` must
be non-empty (enforced by validator) and `next_query_hint` is the LLM's best
guess at a Tavily query that would fill the gap.

```typescript
type ResearchEvalResult = {
  satisfied: boolean;
  gaps: string[];                    // non-empty when satisfied=false
  next_query_hint?: string;
};
```

### `SectionResearchStep` / `SectionResearchLog` — per-section research trace

One `SectionResearchStep` per loop iteration: the LLM-generated Tavily `query`,
the evidence pool size after that iteration's fetch+merge, and the iteration's
`ResearchEvalResult`. A `SectionResearchLog` bundles all steps for one section.
Persisted on the research `StageTrace` via `planning.research_log` (see below).

```typescript
type SectionResearchStep = {
  iteration: number;                 // 1-based
  query: string;                     // LLM-generated Tavily query
  pool_size: number;                 // pool size after this iteration
  eval: ResearchEvalResult;
};

type SectionResearchLog = {
  section_id: string;
  steps: SectionResearchStep[];
};
```

### `ConsistencyCheckOutput` — cross-section consistency

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

### `LLMCall` — one entry per LLM round-trip

```typescript
type LLMCall = {
  model: string;                     // OpenRouter model identifier
  input_tokens: number;
  output_tokens: number;
  cost_usd: number;                  // estimated from a per-model price table
  duration_ms: number;
};
```

### `StagePlanning` — LLM-generated plans/criteria for a planning stage

Captured only on planning stages. The **curation** stage populates
`section_plans` with the full editorial plan that drove research (backbone +
LLM-curated sections, each carrying its `acceptance` criteria). The **research**
stage populates `research_log` with one `SectionResearchLog` per section. Other
stages leave `planning` null.

```typescript
type StagePlanning = {
  section_plans: SectionPlan[];      // curation: the plan + acceptance criteria
  research_log: SectionResearchLog[];// research: per-section query/eval iterations
};
```

### `StageTrace` — one entry per pipeline stage

```typescript
type StageTrace = {
  stage: string;                     // "ground", "extract:reactions", ...
  started_at: ISO8601;
  duration_ms: number;
  model?: string;
  tokens?: { input: number; output: number };
  cost_usd?: number;
  outcome: "success" | "fallback" | "skipped" | "error";
  retry_count: number;
  error?: string;
  output_ref?: string;               // hash or reference, not the full payload
  planning?: StagePlanning;          // present only on curation/research stages
  llm_calls: LLMCall[];              // empty for deterministic stages
};
```

### `EditorAction` — every editor decision captured

```typescript
type EditorAction = {
  action_at: ISO8601;
  actor: string;                     // "cli_user@local" or named editor
  action:
    | "accept_section"
    | "regenerate_section"
    | "edit_section_field"
    | "skip_section"
    | "override_archetype"
    | "override_preset"
    | "approve_page"
    | "reject_page"
    | "save_draft"
    | "comment_section"
    | "add_section";
  target?: {
    section_id?: string;
    field_path?: string;
  };
  before?: unknown;                  // for edits
  after?: unknown;
  reason?: string;                   // "single_source", "auto_mode", user-typed, ...
};
```

In `--auto` mode every HITL prompt still records an `EditorAction` with
`reason: "auto_mode"`.

### `EditorNotes` — plan-review HITL commentary

Collected at the `plan_review` HITL gate. Section-level comments feed the
research-query and block-extract prompts for that section as hard editorial
constraints; `global_comment` applies to every section.

```typescript
type EditorNotes = {
  section_comments: Record<string, string>;  // section_id → free-form note
  global_comment?: string;
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
  | "urgent_light"
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
    whitelist: string[];             // block kinds permitted in the sidebar
  };

  mobile: {
    breakpoint_px: number;           // e.g. 768
    aux_strategy: "inline_after_hero" | "sink_to_bottom" | "interleave";
    aux_priority_in_mobile: string[]; // block kinds, ordered
  };

  design_tokens: {
    palette: PaletteId;
    density: Density;
    typography_scale: TypographyWeight;
  };

  signals: {
    live_pill: boolean;
    sticky_top_strip: "live" | "breaking" | null;
  };
};
```

### Preset library

Defined at runtime as named parameter sets (each preset a complete
`LayoutConfig`). Editor or LLM may override any field per page.

---

## Schema invariants (must always hold)

1. **Every fact-bearing field has at least one citation.** Validation rejects
   any block whose typed data fields lack `source_id` / `citations`.
2. **`RenderedSection.block_data.kind` must equal `RenderedSection.block_kind`.**
   Enforced by the `_block_kind_matches_data` model validator.
3. **Every `source_id` referenced anywhere on the page must exist in
   `EventPage.sources[]`.** Orphan citations are validation errors.
4. **`EventPage.editorial_sections[]` is the only source of page content.**
   Templates never read outside this array (chrome reads `subject`,
   `wikipedia_card`, `hero_image` only).
5. **`timeline` blocks are sidebar-only and backbone-only.** The curation
   planner must not propose them.
6. **Editor actions are append-only.** `EditorAction[]` is never edited or
   reordered after writing.
7. **`ResearchEvalResult.satisfied=false` requires non-empty `gaps`.** Enforced
   by Pydantic validator — the LLM must articulate what is missing.
8. **Grounded fields trace to evidence, not parametric memory.**
   `EventFacts.when` / `where` come from a `supporting_sources` entry's
   `published_at` or in-body date.
