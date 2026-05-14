# UI Polish — Three-Column Topic Page

**Date:** 2026-05-14
**Status:** Draft (pending user review)
**Scope:** Stage 7 (render) + templates/styles only. No pipeline / schema-shape changes unless explicitly called out under "Schema deltas".

---

## 1. Goals

Upgrade the rendered topic page from a single-column editorial scroll into a **three-column reference-style layout** that:

1. Makes structure visible at a glance (left rail = interactive TOC).
2. Pushes time-anchored facts (timeline, key dates, location, Wikipedia-style sidebar reference) out of the main scroll into a **right rail**, so the center column reads as narrative.
3. Tightens the hero into a "particle"-style overview: title + last-updated + variable subtitle + 4 bullet takeaways.
4. Visually separates **facts** from **opinions** (editor-configurable).
5. Treats quotes as a designed component, not a list — stakeholder-first, with author imagery when available.
6. Replaces the bulleted sources footer with a contained "Sources" card.

Out of scope: live update logic (subtitle is variable in *schema* — refresh cadence is a separate project), real-time Wikipedia API, video transcoding.

---

## 2. Layout

### Desktop (≥ 1200px)

```
┌─────────────────────────────────────────────────────────────────────┐
│  Header chrome: brand · "Last updated 2h ago" · share               │
├──────────┬─────────────────────────────────────┬────────────────────┤
│          │                                     │                    │
│  TOC     │  HERO                               │  REFERENCE PANEL   │
│  (left   │  ├─ badge                           │  ├─ Wikipedia card │
│   rail   │  ├─ H1 title + last-updated chip    │  │   (summary +    │
│   220px  │  ├─ subtitle (variable)             │  │   infobox rows) │
│   sticky)│  └─ 4 bullets "Overview"            │  │                 │
│          │                                     │  ├─ Timeline       │
│  ▸ Why   │  ── center scroll ──                │  │   (milestones,  │
│    now   │  Need section 1 (Facts)             │  │   date · place) │
│  ▸ What  │     paragraph / factsheet           │  │                 │
│  ▸ When  │  Need section 2 (Opinions)          │  └─ Key facts      │
│  ▸ Who   │     quotes (stakeholder-first)      │      pill list     │
│   reacts │  Need section 3 …                   │                    │
│  ▸ ...   │                                     │  (sticky, scrolls  │
│          │  SOURCES box                        │   independently    │
│          │                                     │   within viewport) │
└──────────┴─────────────────────────────────────┴────────────────────┘
   240px              ~700–820px                       300px
```

Grid: `grid-template-columns: 240px minmax(0, 1fr) 320px;` with `gap: 40px` and a `max-width: 1320px` container.

### Tablet (768–1199px)

Two columns: left TOC collapses into a **drawer** (hamburger button, slides in). Right reference panel stays. Center widens.

### Mobile (< 768px)

Single column. TOC becomes a sticky top "Jump to" dropdown. Reference panel content is interleaved inline at semantically appropriate breakpoints (timeline after hero, Wikipedia card after first need section, key facts at bottom).

---

## 3. Components

### 3.1 Hero ("Particle")

Replaces existing `chrome/hero.html`.

- Badge (optional, e.g. "Live", "Upcoming") — color from aesthetic palette.
- **H1 title** + inline `<time>` chip rendering `meta.last_updated` as "Updated 2h ago" with `title` tooltip showing absolute ISO.
- **Subtitle** — pulled from `HeroData.subtitle`. Already in schema as variable per-update; no schema change.
- **Overview bullets** — 4-item list, ≤ 18 words each. Sourced from a new `HeroData.overview_bullets: list[OverviewBullet]` field.
  - `OverviewBullet { text: str, source_id: SourceId }`
  - Min 3, max 4. Extraction prompt updated in `modules/hero.py`.
- Hero image: keep, but enlarge and require `image_url` to be HTTPS, ≥ 1200px wide. Add `<picture>` with srcset breakpoints (1200/800/480). Fallback caption: "Photo: {publisher_name}".

**Schema delta:** `HeroData` gains optional `overview_bullets`. Backwards-compatible (default None; template falls back to old summary).

### 3.2 Left TOC rail (`chrome/toc.html`)

- Vertical list of need sections in plan rank order.
- Sticky (`position: sticky; top: 24px`); independently scrolling if list overflows viewport.
- **Active section tracking** via IntersectionObserver — current section gets accent bar + bold label.
- **Hover affordance**: on mouse-enter of a TOC item, show a small popover with the section's `rationale` (already on `NeedSection`) and the count of blocks inside. ~280px wide, 120ms fade.
- Keyboard accessible (arrow keys move focus, Enter activates).
- Each entry: `▸ {section.title}` with a thin progress dot indicating whether user has scrolled past.

No new schema fields — driven entirely by existing `sections`.

### 3.3 Right reference panel (`chrome/reference.html`)

Three stacked cards. Each card is collapsible (`<details>` element, open by default desktop / closed mobile).

1. **Wikipedia card** — new module surface, see §4.
2. **Timeline card** — relocated from main scroll. See §3.5.
3. **Key facts pills** — derived from `InfoboxModule` if present. Compact label/value rows, no table chrome.

Sticky like the TOC. If total height exceeds viewport, the panel scrolls inside its own container.

### 3.4 Facts vs Opinions sectioning

In the center scroll, each need section gets a `category` tag rendered as a small chip above the title:

- `FACT` (gray) — for needs whose modules are factual (infobox, schedule, kpi_numbers, comparison, where_to_watch, background, changelog).
- `OPINION` (palette accent) — for `reactions`, `media_coverage` (when grouped `by_perspective`), `official_statements`.
- Optional editor-defined sub-tag for opinions (e.g. "Industry view", "Public reaction"). Editor configures via HITL plan-review step.

**Schema delta:** `NeedPlan` gains `category: Literal["fact","opinion"] | None` and `opinion_subtag: str | None`. Inferred by default from the assigned module kinds (mapping table in `pipeline/plan.py`); editor can override.

### 3.5 Timeline (moved to right rail, redesigned)

- Source: existing `ScheduleData` or a new `MilestoneTimelineData` (see schema delta).
- Render style: vertical rail with date markers, NOT a horizontal sparkline.
  - Each entry: `date` (large), optional `time` (smaller, same line), `label`, optional `location` with a tiny pin icon.
  - "Past" milestones are dimmed (40% opacity); current/next is highlighted; future are normal.
- Compact: max ~6 visible, with "Show all" expander if more.

**Schema delta:** Either reuse `ScheduleData.items` (`time_iso`, `label`, `location` already present) and render only milestones flagged `is_milestone: bool` — OR introduce a focused `MilestonesModule`. Recommendation: **add `is_milestone: bool = False` to `ScheduleItem`**, default False, populated by the schedule extraction prompt. Lower-risk than a new module.

### 3.6 Quotes (`blocks/reactions.html`, new)

Reactions are currently embedded via a generic block. Give them dedicated rendering:

- 2–4 quote cards max (cap below current schema `max_length=15` — pipeline picks top N by `stakeholder_priority`).
- **Stakeholder ranking**: prompt update in `modules/reactions.py` to score each reaction author as `stakeholder | adjacent | third_party` and prefer stakeholders.
- Card design:
  - Author photo (circle, 64px) — sourced from OpenGraph scrape of the source URL OR Wikidata image lookup. Falls back to monogram chip with author initials over palette color.
  - Author name (bold) + role (muted).
  - Quote: large serif, with prominent opening glyph (`"`), no surrounding quote marks in body. Max one quote per card, ≤ 280 chars (already enforced).
  - Sentiment dot in corner (green/gray/red).
  - Source citation as superscript link.
- Static — no carousel, no auto-rotate.

**Schema delta:** `ReactionItem` gains optional `author_image_url: HttpUrl | None` and `stakeholder_tier: Literal["stakeholder","adjacent","third_party"]`. Author image populated opportunistically; missing is fine.

### 3.7 Sources card (replaces footer `<ol>`)

- Container: bordered card with header "Sources" + count chip.
- Body: grid of source rows, two columns on desktop, one on mobile.
- Each row: publisher favicon (16px) · publisher name · tier badge · linked title · published date.
- No bullet/number markers. The `id="src-{n}"` anchors stay (footnotes still link in).
- Card lives at the **end of the center column**, not in the `<footer>`. The `<footer>` keeps only meta line + brand.

---

## 4. Wikipedia integration

A new optional pipeline addition (can land in a follow-up; spec captures the contract).

- New stage helper `sources/wikipedia.py` (alongside `wikidata.py`).
- Called from Stage 2 (disambiguate) once the primary entity is resolved to a Wikidata QID. Fetches the Wikipedia REST summary endpoint for the linked title in `en`.
- Stores result on `EventPage` as `wikipedia_card: WikipediaCardData | None` (new top-level field, optional).
  - `{ title, summary_html_safe, thumbnail_url, infobox_rows: [{label, value}], article_url, retrieved_at }`
  - `summary_html_safe` is the plain-text extract, length-capped to ~600 chars.
- Template: `chrome/reference.html` renders this as the top reference card. Includes "from Wikipedia" attribution + CC-BY-SA notice + article link.
- If Wikipedia fetch fails or QID has no enwiki sitelink, omit the card silently.

This integration is **additive**. It does not replace any pipeline-extracted module.

---

## 5. Media policy

- **All images** rendered on the page must be HTTPS, ≥ 800px wide, and carry an alt text. Pipeline already collects og:image; tighten the fetch step to discard images below the threshold.
- **Videos** (new): if a source URL is YouTube/Vimeo/native MP4 and is tagged `is_video: true` during fetch, allow a `media` block to embed a lazy-loaded iframe. Off by default behind a feature flag (`ENABLE_VIDEO_BLOCKS`). Captions and attribution required.
- All media has a visible attribution line: "Photo / Video: {publisher}".

Schema delta: `Source` gains optional `media_kind: Literal["image","video","article"] | None` and `media_url: HttpUrl | None`. Fetch stage populates.

---

## 6. Files touched

```
templates/
  layout.html                  [rewrite: 3-col grid]
  chrome/
    hero.html                  [rewrite: bullets, last-updated chip]
    nav.html                   [DELETED — replaced by toc.html]
    toc.html                   [NEW]
    reference.html             [NEW]
    reference_wikipedia.html   [NEW partial]
    reference_timeline.html    [NEW partial]
    reference_keyfacts.html    [NEW partial]
  needs/
    section.html               [add category chip, opinion subtag]
  blocks/
    reactions.html             [NEW: dedicated quote card grid]
    timeline.html              [keep for inline use, but center col now rarely uses]
  partials/
    sources_card.html          [NEW: replaces footer <ol>]
  styles.css                   [significant rewrite — grid, cards, dark/palette tokens]
  toc.js                       [NEW: ~40 LOC for IntersectionObserver active state]

src/generator/
  schema.py                    [additive fields, see §3 deltas]
  modules/hero.py              [overview_bullets in prompt]
  modules/reactions.py         [stakeholder_tier + image scraping]
  modules/schedule.py          [is_milestone flag]
  pipeline/plan.py             [default category inference]
  pipeline/render.py           [pass wikipedia_card + categorized sections to template]
  sources/wikipedia.py         [NEW]
  blocks/converter.py          [add reactions → reactions-card mapping]
```

---

## 7. Testing

- **Visual snapshot tests** are out of scope (no existing harness). Instead:
- Unit tests for new schema fields' validators (`tests/test_schema.py`).
- `tests/pipeline/test_plan.py` — fact/opinion default inference.
- `tests/modules/test_hero.py` — overview_bullets prompt round-trip with fixture LLM.
- `tests/integration/test_render_three_column.py` — render a canned `EventPage` and assert HTML contains: TOC nav landmark, reference aside landmark, `category="fact"` and `category="opinion"` chips, sources card (not `<ol>` in `<footer>`).
- Accessibility: each landmark (`<nav aria-label="Sections">`, `<aside aria-label="Reference">`, `<main>`) must be present and unique. Skip-link still works.

---

## 8. Rollout

Single PR is too big. Suggested decomposition:

1. **PR-A:** Three-column layout shell + TOC (no schema changes). Hero stays as-is.
2. **PR-B:** Hero overview bullets + facts/opinions chips.
3. **PR-C:** Reactions card redesign + stakeholder ranking + author images.
4. **PR-D:** Timeline relocation + milestone flag.
5. **PR-E:** Sources card.
6. **PR-F:** Wikipedia card (depends on PR-A's reference panel).

Each PR is independently shippable and visually verifiable.

---

## 9. Open questions / explicit deferrals

- **Subtitle update cadence.** Schema field exists; refresh logic is a separate project. Spec assumes single-shot generation for now.
- **i18n.** All copy is en-US. The "Updated 2h ago" relative-time helper will need an i18n shim later — out of scope here.
- **Wikipedia license display.** Card includes attribution + CC-BY-SA notice; legal sign-off not required for prototype but should be flagged before any external launch.
- **Author photos** — Wikidata image lookup is best-effort. No P2 fix if missing; monogram fallback is the design.

---

## 10. Success criteria

A generated topic page:

1. Renders three columns on desktop, collapses gracefully on tablet/mobile.
2. TOC tracks the active section as user scrolls; hover reveals rationale.
3. Hero shows title + last-updated + subtitle + exactly 3–4 overview bullets.
4. Each need section displays a `FACT` or `OPINION` chip.
5. Reactions render as ≤ 4 quote cards, stakeholder-first, with photo-or-monogram.
6. Timeline appears in the right rail, milestones-only, with date + optional time + optional location.
7. Sources appear in a bordered card at the end of center column (no `<ol>` in `<footer>`).
8. Wikipedia card (if available) renders in the right rail with attribution.
9. All on-page images are ≥ 800px wide and have non-empty alt text.
10. Lighthouse a11y ≥ 95 on the smoke-test fixture.
