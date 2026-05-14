# Design Document — Topic Page Generator

> Evaluator-facing design document for the Newsbreak take-home. Currently a scaffold; sections will be filled in as implementation proceeds. See [`PRD.md`](./PRD.md) for the planning view and [`schema.md`](./schema.md) for the full data contract.

## Contents

1. [Product decisions](#1-product-decisions)
2. [System architecture](#2-system-architecture)
3. [Prompt and data contract](#3-prompt-and-data-contract)
4. [Information sourcing](#4-information-sourcing)
5. [Failure modes](#5-failure-modes)
6. [What I'd do with another week (Future Work)](#6-future-work)

---

## 1. Product decisions

**AI drafts, editor publishes — in that order, always.** The system generates a complete draft topic page and presents it to the newsroom editor for review and approval. The editor never writes content; they accept, regenerate, or discard what the system produces. This is the product position locked in PRD §1 and §4. The reversal — editor writes, AI assists — is a different product and was not considered.

**Why this position.** Topic pages for breaking news require speed (editors need to ship within minutes) and source discipline (every claim must be traceable). Pure automation fails the second requirement without human review. Pure manual work fails the first. The five-touchpoint HITL design (low-confidence triage, disambiguation, plan override, per-module review, final approval gate) enforces this discipline at the points where the pipeline is most likely to be wrong, not everywhere.

**The content posture dividing line.** We synthesize commodity facts and route original journalism back to its source. If the content could be a Wikidata-style field — a date, a venue, a version number, a headcount — the system writes it as prose and cites the source. If the content is a sentence in a specific journalist's article — an analyst's take, a named reaction, a reporter's scoop — the system quotes ≤30 words and links out. This rule is enforced at the schema layer: `Reactions` items carry verbatim quotes with `source_id`; `OfficialStatements` items carry verbatim quotes with `source_url`. Nothing is paraphrased where the original wording matters legally or editorially.

**Why four named aesthetic presets, not a free-form layout generator.** The closed library (`live_dominance`, `product_focus`, `imminent_event`, `reference`) solves two problems. First, it gives the LLM creative latitude without open-ended HTML generation — the model picks a preset identifier and a palette from enumerated options; it never writes CSS. Second, it makes the output predictable: an evaluator or editor knows exactly what the four presets look like before opening a page. The `reference` preset is the deliberate fallback when the LLM is below the aesthetic confidence threshold, ensuring a coherent result even when the event type is unusual.

**Newsbreak as the publishing context.** Newsbreak is a local-news aggregator whose value to readers is surfacing relevant regional and national coverage fast. Topic pages — structured, fact-first summaries — fit that context better than long-form articles, which Newsbreak's partner publishers already produce. The system is designed to strengthen the partner-economy flywheel (see §6 for the deferred partner-publisher integration) rather than compete with it. Every `MediaCoverage` module routes readers back to partner and independent publishers.

**Trade-offs explicitly accepted in v1.** No real-time post-publish updates: the page reflects the evidence pool at generation time. No embed-rich layouts (video players, live score widgets): vanilla HTML keeps the output portable and auditable. English output only: localization adds extraction complexity that is out of scope for the one-week build. These are not oversights; they are recorded in PRD §2 as explicit out-of-scope items.

---

## 2. System architecture

**The four-layer abstraction.** The system is organized as four layers, each a typed contract whose only input is the previous layer's output:

1. **Input** — a one-sentence event description, classified into an `event_type_hint`, `temporal_posture`, and `primary_entity` by Stage 1 (Triage).
2. **Plan** — a composition of module kinds, slot assignments, and an aesthetic preset, produced deterministically by Stage 3a from a lookup table keyed on archetype, then refined by the LLM in Stage 3b.
3. **Evidence** — the raw evidence pool: a list of `Source` records fetched in parallel by Stage 4 from Wikipedia, Wikidata, and Tavily. This pool is immutable after Stage 4; all downstream stages read from it, none add to it.
4. **Render** — the `EventPage` object, assembled from typed `TypedModule` records by Stage 5 and 6, then converted to HTML and `data.json` by Stage 7. Both the HTML and the JSON artifact are produced from the same `EventPage` instance — it is the single source of truth.

**The eight pipeline stages.**

```
Input → [1] Triage → [2] Disambiguate → [3a] Plan → [3b] Aesthetic Plan
      → [4] Fetch → [5] Extract → [6] Consistency → [7] Render → [8] Trace
```

- **Stage 1 Triage**: LLM classifies the input sentence, assigns confidence, lists alternatives if ambiguous.
- **Stage 2 Disambiguate**: LLM + Tavily resolves ambiguity when triage confidence falls below 0.85.
- **Stage 3a Plan**: Deterministic lookup maps archetype to module composition and slot routing.
- **Stage 3b Aesthetic Plan**: LLM picks preset ID, palette, hero mood, and copy register from closed enums.
- **Stage 4 Fetch**: Parallel HTTP to Wikipedia, Wikidata, and Tavily; no LLM; builds the evidence pool.
- **Stage 5 Extract**: LLM extracts each module's typed data from the evidence pool, with citations required.
- **Stage 6 Consistency**: LLM re-reads the evidence pool and checks cross-module coherence; flags contradictions.
- **Stage 7 Render**: Deterministic Jinja2 templating produces HTML from the `ResolvedLayout` object.
- **Stage 8 Trace**: Deterministic file I/O writes `data.json` and `trace.json` alongside the HTML.

**Why a bounded pipeline, not a free agentic loop.** A free loop — where the LLM decides what to fetch next, which modules to generate, and when to stop — is difficult to audit and harder to make deterministic enough for editor trust. The bounded pipeline puts LLMs only at the fuzzy semantic tasks (classification, extraction, taste judgment) and keeps routing, fetching, and rendering as deterministic code. Every stage's output is a typed Pydantic object; if it does not validate, the stage retries or falls through with `outcome=fallback`, never silently corrupts downstream stages.

**`EventPage` as the single source of truth.** Both the HTML template and the `data.json` artifact are produced from one `EventPage` instance. The template reads from `EventPage.modules[]`; nothing else. Editor overrides written into `EventPage.layout.overrides` are the only mechanism for modifying the rendered output after Stage 7.

---

## 3. Prompt and data contract

**Structured outputs everywhere.** Every LLM call in the pipeline uses OpenRouter's `response_format` parameter to enforce a JSON schema on the model's reply. There is no free-text parsing, no regex extraction, no "parse the markdown table" post-processing. The model either returns a valid structured object or the stage retries. This is the primary mechanism that makes the system auditable: if the output parsed, it conforms to the contract.

**Citations are mandatory at the schema layer.** Every fact-bearing field in every module schema carries a `source_id` (scalar) or `citations` (array of `Citation` objects). Schema validation rejects any module whose typed data fields lack these references. This is schema invariant #1 in `schema.md`: "Every fact-bearing field has at least one citation." The LLM is prompted with the evidence pool indexed by source ID and instructed to assign a `source_id` to every field it populates. A claim the LLM cannot trace to the evidence pool must be left empty or omitted — it cannot invent a source ID, because orphan citations (source IDs that do not appear in `EventPage.sources[]`) are also schema validation errors (invariant #3).

**The trust boundary.** The schema is the trust boundary between the LLM and the editor. If a module parses, it means: (a) every fact carries a citation, (b) every citation points to a real source in the evidence pool, (c) the module's confidence signals are populated and the editor can read them. The editor does not need to re-verify the LLM's internal reasoning — they verify the citations. This is what makes the five-minute edit-and-approve workflow viable.

**Prompt structure.** Each LLM stage receives a base preamble (system prompt, injected once) that describes the pipeline's purpose, the evidence-pool format, and the citation rules. Stage-specific instructions follow as the user turn. For module extraction (Stage 5), each module kind has its own extraction prompt that names the target schema type and lists the fields the LLM must populate. Aesthetic choices (Stage 3b) are bounded to closed string enums — the LLM picks from `AestheticPresetId`, `PaletteId`, `HeroMood`, `CopyRegister`; it never generates free-form style directives.

**Retry behavior.** On schema-validation failure, the stage retries once with a stricter prompt that includes the validation error message. On second failure, the stage records `outcome=fallback` in the trace and either drops the module or substitutes a minimal valid placeholder. No stage loops indefinitely. The retry count and error string are recorded in `StageTrace.retry_count` and `StageTrace.error`, so the evaluator can see exactly when and why a fallback was invoked.

The complete type definitions for every stage's output — including the discriminated union of all 12 module kinds — live in `schema.md`. The Pydantic models in `src/schema.py` are generated directly from that document and are the runtime enforcement of this contract.

---

## 4. Information sourcing

**Tavily as the primary search backend.** Tavily is called in Stage 4 for fresh news and recent coverage. It was chosen over raw web scraping for two reasons: latency (structured results arrive in one round-trip without HTML parsing) and curation (Tavily's index skews toward well-sourced news rather than SEO-farmed content). The `tavily-python` wrapper was dropped in favor of direct `httpx.AsyncClient` calls against `https://api.tavily.com/search`, which keeps a single mocking story for the test suite (see §6 for the full explanation). Wikipedia and Wikidata are fetched separately via their REST APIs for stable background facts and entity metadata.

**Source tier scoring.** Every `Source` record carries a `publisher.tier` field drawn from the `SourceTier` enum:

- `T0` — primary/official sources: the event's own site, government pages, corporate IR.
- `T1` — independent tier-1 news: Reuters, AP, BBC, Bloomberg, NYT.
- `T2` — Wikipedia and Wikidata.
- `T3` — other public web: regional outlets, trade press, blogs.

The source-ranking algorithm uses tier as the primary sort key, then publication recency as a tiebreaker. The `PlanOutput.source_strategy.preferred_tiers` field lets each archetype bias toward different tiers — a product launch prefers T0 (official announcement) and T1; a live cultural event may accept more T3 for social pulse data.

**The evidence pool is immutable after Stage 4.** This is a deliberate constraint. Once the fetch stage completes, the pool is sealed. Stage 5 (Extract) reads from it; Stage 6 (Consistency) reads from it; the `regen-module` CLI subcommand reads from it. Nothing adds to it after Stage 4. This is what makes per-module regeneration cheap: regenerating a single module does not trigger a re-fetch. It also means the editor can always audit which sources were available when the page was generated — the pool is written into `data.json` verbatim.

**Sourcing failure modes.** Two are handled explicitly. First, no Tavily results: the stage falls back to a single-source assertion using whatever Wikipedia or Wikidata returned, marks the affected sources with `low_signal=true`, and records the condition in the trace. Second, Tavily rate limits: the `tenacity` retry decorator applies exponential backoff with a single retry before the stage aborts and records `outcome=error`. On abort, the pipeline falls through with whatever sources were fetched before the limit was hit — partial evidence is better than a complete stop, as long as the trace records the gap.

**AI-content blacklist.** Sourcing explicitly excludes URLs from known AI-content farms. This was listed as a locked-in decision in PRD §4, motivated by the Reuters investigation finding 40+ AI-misinfo incidents in news aggregators. The blacklist is a static list of domains checked at fetch time; any result whose URL matches is dropped before it enters the evidence pool.

---

## 5. Failure modes

**Hallucination defenses, in order of strength.**

1. **Schema-validated structured outputs.** Every LLM call returns a typed JSON object validated against a Pydantic model. A claim that does not fit the schema cannot appear in the output — the response is rejected and retried, not accepted with a warning.

2. **Citation required on every fact.** Every fact-bearing field must carry a `source_id` pointing into the evidence pool. The LLM is instructed that unprovable claims must be omitted. Schema validation enforces this: a field with a missing or orphan citation is a validation error, not a soft warning.

3. **Stage 6 consistency check.** After all modules are extracted, a dedicated LLM pass re-reads the evidence pool and cross-checks module content for contradictions — date mismatches, conflicting numbers, quoted claims that don't appear in any source. Issues are returned as `ConsistencyCheckOutput.issues[]` with severity (`warning` or `error`) and recommended action (`regenerate`, `remove`, or `manual_review`). Errors block the final approval gate; warnings surface in the trace.

**Low-confidence escape hatch: the five HITL touchpoints.** When the pipeline is uncertain, it does not guess silently — it surfaces a decision to the editor. The five touchpoints are: (1) low-confidence triage, where the editor picks from alternative event interpretations; (2) unresolved disambiguation, where the editor clarifies ambiguous input; (3) plan override, where the editor confirms or adjusts the module composition; (4) per-module review, where the editor accepts, regenerates, edits, or skips any module flagged below the confidence threshold; (5) final approval gate, where the editor reviews the rendered page in a browser before publishing.

**What `--auto` trades away.** The `--auto` flag bypasses all five touchpoints. Every auto-decision is logged in the trace with `reason: "auto_mode"`. The final `Trace.final_outcome` is set to `"auto_approved"`, which is distinct from `"approved_published"` (editor-reviewed). Reviewers can therefore distinguish auto-published pages from editor-approved pages by reading the trace. Auto mode is intended for batch demo runs, not production publishing.

**Known weaknesses accepted in v1.**

(a) We do not detect adversarial sources. If a single T0-tier source (e.g., an official-looking domain) contains fabricated information, the system will treat it as authoritative. The AI-content blacklist catches known bad actors but does not detect novel ones.

(b) We do not re-check facts after publish time. There is no staleness watcher. A page generated before a correction or retraction is issued will not automatically update. The `meta.last_updated` field records when the page was generated; staleness detection is a §6 future item.

(c) The editor sees a draft once, at the final approval gate. There is no per-section diff UI showing what changed between a module regeneration and its previous version. The editor must re-read the affected module. This is a deliberate scope cut — the CLI + browser preview loop is sufficient for expert users who know what they are approving.

---

## 6. Future Work

Items deferred from the one-week scope. Each is logged with the reason for deferral and the rough shape of the eventual implementation.

### Newsbreak partner-publisher integration

The system is designed to give a small ranking preference to publishers that have a formal partnership with Newsbreak, on the grounds that doing so strengthens the partner-economy flywheel the aggregator depends on. This was deferred because the partner-publisher list is not currently available to me as a candidate. When the partner data is integrated, the following changes apply:

- **`SourceTier` gains a new `T2` partner tier**, reinserted between the current T1 (independent news) and the current T2 (Wikipedia/Wikidata). All current T2/T3 values renumber accordingly.
- **`Source.publisher` gains an `is_newsbreak_partner: boolean` field**, populated from the partner registry at fetch time.
- **The source-ranking algorithm gains a `partner_boost` term** capped at +15% of a publisher's base score — large enough to break ties between equivalent peer-tier sources, small enough to never override factual hierarchy (a partner blog will never outrank a Reuters scoop on a contested fact).
- **`Source.rights.max_excerpt_words`** becomes per-contract for T2 partner sources, instead of the uniform 30-word cap currently applied to all non-T0 tiers.
- **`MediaCoverage` rendering** adds a subtle "Featured in your feed" badge or color bar on partner items, reinforcing partner visibility without disrupting the list ranking.

Implementation surface is small (one new field on `Source`, one rerank term, one rendering hint), but the data integration with Newsbreak's partner registry is the gating item.

### Dependency deviation from PRD §5

PR 2 dropped `tavily-python` from the runtime dependency list. The Tavily HTTP API is called directly via `httpx.AsyncClient` against `https://api.tavily.com/search`. The reason: `tavily-python` uses `requests` under the hood, which `respx` cannot intercept, so test-suite HTTP mocking would require a parallel `responses`-based stack. Going direct keeps a single mocking story (`respx` for all clients) and removes one dependency. The PRD-stated count of nine runtime dependencies becomes eight after this PR. No functional impact on output or behavior.

### Other items

*[Additional Future Work items will be added here as they emerge during implementation.]*
