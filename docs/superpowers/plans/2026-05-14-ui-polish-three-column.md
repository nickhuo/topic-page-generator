# UI Polish — Three-Column Topic Page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the rendered topic page from a single-column editorial scroll into a three-column reference layout with an interactive TOC, a right reference rail (Wikipedia card + milestones + key facts), redesigned reactions, fact/opinion chips, a sources card, and a particle-style hero.

**Architecture:** Stage-7 (render) and template-only changes plus additive schema fields. No restructuring of pipeline stages. Six independently shippable PRs (A→F), each ending in green tests and a commit.

**Tech Stack:** Python 3.12, `uv` toolchain, Pydantic v2, Jinja2, pytest (`asyncio_mode = auto`), respx for HTTP mocks, selectolax + httpx (existing OG scrape), plain CSS + ~40 LOC of vanilla JS.

**Spec:** `docs/superpowers/specs/2026-05-14-ui-polish-three-column-design.md`.

---

## File Structure

| Path | Action | Responsibility |
|---|---|---|
| `templates/layout.html` | Rewrite | Three-column grid shell, landmarks, slot for TOC / main / aside. |
| `templates/chrome/hero.html` | Rewrite | Particle hero: title + last-updated chip + subtitle + 3–4 bullets. |
| `templates/chrome/nav.html` | Delete | Replaced by `toc.html`. |
| `templates/chrome/toc.html` | New | Sticky left rail, sections list, hover popovers. |
| `templates/chrome/reference.html` | New | Right rail container, includes the 3 reference cards. |
| `templates/chrome/reference_wikipedia.html` | New | Wikipedia card partial. |
| `templates/chrome/reference_timeline.html` | New | Milestones-only timeline partial. |
| `templates/chrome/reference_keyfacts.html` | New | Key-facts pill list from infobox. |
| `templates/needs/section.html` | Modify | Add FACT/OPINION chip + opinion subtag. |
| `templates/blocks/reactions.html` | New | Dedicated quote-card grid. |
| `templates/partials/sources_card.html` | New | Replaces bulleted `<ol>` in footer. |
| `templates/toc.js` | New | IntersectionObserver active-state for TOC. |
| `templates/styles.css` | Rewrite | New grid + cards + chips + quote-card + chip tokens. |
| `src/generator/schema.py` | Modify | Additive: `HeroData.overview_bullets`, `ScheduleItem.is_milestone`, `ReactionItem.author_image_url` + `stakeholder_tier`, `NeedCurationPlan.category` + `opinion_subtag`, `EventPage.wikipedia_card`, `Source.media_kind` + `media_url`, new `WikipediaCardData`, new `OverviewBullet`. |
| `src/generator/modules/hero.py` | Modify | Prompt asks for `overview_bullets`. |
| `src/generator/modules/reactions.py` | Modify | Prompt asks for `stakeholder_tier`; ranking helper. |
| `src/generator/modules/schedule.py` | Modify | Prompt asks for `is_milestone`. |
| `src/generator/pipeline/plan.py` | Modify | Default fact/opinion category inference. |
| `src/generator/pipeline/render.py` | Modify | Pass `categorized_sections`, `reference_panel`, `wikipedia_card`, milestones to template. |
| `src/generator/blocks/converter.py` | Modify | New `reactions` block kind mapping. |
| `src/generator/sources/wikipedia.py` | New | Wikipedia REST summary fetch + parse. |
| `tests/test_schema.py` | Modify | New field validators. |
| `tests/pipeline/test_plan.py` | Modify | Category inference. |
| `tests/modules/test_hero.py` | New (if missing) | Hero prompt + parse fixture. |
| `tests/sources/test_wikipedia.py` | New | Wikipedia fetch + failure path. |
| `tests/integration/test_render_three_column.py` | New | End-to-end render assertions. |

---

## Conventions

- **Toolchain:** `uv sync` after any `pyproject.toml` change. All commands run via `uv run …`.
- **Test runner:** `uv run pytest -q` (top-level) or `uv run pytest path::test_name -v` for single test.
- **Lint/format:** After each PR, run `uv run ruff check . && uv run ruff format .`. Treat ruff failures as build failures.
- **Commits:** One commit per task at minimum. Conventional-commit style (`feat:`, `refactor:`, `test:`, `docs:`).
- **TDD discipline:** Every behaviour change starts with a failing test. Schema validator changes test the validator directly. Template changes test through the integration render fixture.

---

# PR-A — Three-column layout shell + TOC

Schema-free. Replaces nav with TOC, introduces grid + landmarks. No content changes.

### Task A1: Integration fixture for rendered HTML

**Files:**
- Create: `tests/integration/conftest.py`
- Create: `tests/integration/test_render_three_column.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/integration/test_render_three_column.py
from generator.pipeline.render import render_html
from tests.fixtures import canned_event_page  # see Step 3


def test_layout_has_three_column_landmarks():
    page = canned_event_page()
    html = render_html(page)
    assert 'aria-label="Sections"' in html        # left TOC <nav>
    assert 'aria-label="Reference"' in html       # right <aside>
    assert '<main id="main"' in html
    assert 'class="page-grid"' in html


def test_layout_no_longer_uses_old_nav_chrome():
    page = canned_event_page()
    html = render_html(page)
    assert 'class="needs-nav"' not in html        # old chrome/nav.html marker
```

- [ ] **Step 2: Add the fixture helper**

```python
# tests/integration/conftest.py
import pytest

from tests.fixtures import canned_event_page  # re-export for tests


@pytest.fixture
def event_page():
    return canned_event_page()
```

If `tests/fixtures.py` lacks `canned_event_page`, add it now:

```python
# tests/fixtures.py  (append)
from datetime import datetime, timezone

from generator.schema import (
    AestheticPresetId, EventLayout, EventMeta, EventPage, EventSubject,
    HeroData, HeroModule, ModuleConfidence, NeedCurationPlan, Source, SourceTier,
    PublisherInfo,
)


def _src(i: int) -> Source:
    return Source(
        id=f"s{i}",
        url=f"https://example.com/a{i}",
        title=f"Title {i}",
        publisher=PublisherInfo(name=f"Pub{i}", tier="primary"),
        published_at="2026-05-14T00:00:00Z",
    )


def canned_event_page() -> EventPage:
    now = datetime.now(timezone.utc).isoformat()
    hero = HeroModule(
        id="m_hero",
        confidence=ModuleConfidence(overall=0.9, flags=[]),
        data=HeroData(
            title="Sample Event",
            subtitle="A subtitle",
            summary="One-sentence summary of the event.",
            image_alt="",
            badge_label="LIVE",
        ),
    )
    plan = NeedCurationPlan(
        need_id="what_happened",
        activated=True,
        rank=1,
        section_title="What happened",
        rationale="Establish the core facts.",
        assigned_modules=["hero"],
    )
    return EventPage(
        page_id="p_test",
        input_sentence="Sample event happened today.",
        generated_at=now,
        subject=EventSubject(
            primary_entity="Sample Event",
            event_type_hint="generic",
            temporal_posture="recent",
        ),
        modules=[hero],
        layout=EventLayout(preset_id="reference", overrides=None),
        sources=[_src(1)],
        needs_coverage={"what_happened": ["m_hero"]},
        uncovered_needs=[],
        need_plans=[plan],
        meta=EventMeta(
            last_updated=now, editor_approved=True,
            editor_id="test", pipeline_trace_id="t1",
        ),
    )
```

If any imported name (e.g. `PublisherInfo`) doesn't match the real schema, grep `src/generator/schema.py` for the correct symbol and substitute; do not invent fields.

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_render_three_column.py -v`
Expected: FAIL — current `layout.html` has no `page-grid` class and still uses `class="needs-nav"`.

- [ ] **Step 4: Commit the failing test**

```bash
git add tests/integration/test_render_three_column.py tests/integration/conftest.py tests/fixtures.py
git commit -m "test: integration fixture and failing 3-column layout assertions"
```

### Task A2: Rewrite layout.html into three-column grid

**Files:**
- Modify: `templates/layout.html`
- Create: `templates/chrome/toc.html`
- Create: `templates/chrome/reference.html` (stub)
- Delete: `templates/chrome/nav.html`

- [ ] **Step 1: Replace `layout.html`**

```html
<!-- templates/layout.html -->
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{{ page.subject.primary_entity }} — Topic Page</title>
  <style>{{ palette_css_block | safe }}</style>
  <style>{{ stylesheet | safe }}</style>
  <script type="application/ld+json">{{ jsonld | safe }}</script>
</head>
<body>
  <a class="skip-link" href="#main">Skip to content</a>

  <header class="page-chrome">
    {% if hero_module %}
      {% include "chrome/hero.html" %}
    {% endif %}
    {% if countdown_module %}
      {% include "chrome/countdown.html" %}
    {% endif %}
  </header>

  <div class="page-grid">
    {% if sections %}
      {% include "chrome/toc.html" %}
    {% endif %}

    <main id="main" class="page-main">
      {% for section in sections %}
        {% include "needs/section.html" %}
      {% endfor %}
      {% include "partials/sources_card.html" ignore missing %}
    </main>

    {% include "chrome/reference.html" ignore missing %}
  </div>

  <footer class="page-footer">
    <div class="container">
      <p class="meta-line">Last updated {{ page.meta.last_updated }}</p>
    </div>
  </footer>

  <script>{{ toc_js | safe }}</script>
</body>
</html>
```

- [ ] **Step 2: Create the TOC partial**

```html
<!-- templates/chrome/toc.html -->
<nav class="page-toc" aria-label="Sections">
  <ol class="page-toc__list">
    {% for section in sections %}
      <li class="page-toc__item" data-target="need-{{ section.need_id }}">
        <a href="#need-{{ section.need_id }}" class="page-toc__link">
          <span class="page-toc__dot" aria-hidden="true"></span>
          <span class="page-toc__label">{{ section.title }}</span>
        </a>
        {% if section.rationale %}
          <div class="page-toc__popover" role="tooltip">{{ section.rationale }}</div>
        {% endif %}
      </li>
    {% endfor %}
  </ol>
</nav>
```

- [ ] **Step 3: Create reference rail stub**

```html
<!-- templates/chrome/reference.html -->
<aside class="page-reference" aria-label="Reference">
  {# Cards populated in PR-D / PR-F. Empty stub keeps the landmark stable. #}
  {% include "chrome/reference_timeline.html" ignore missing %}
  {% include "chrome/reference_keyfacts.html" ignore missing %}
  {% include "chrome/reference_wikipedia.html" ignore missing %}
</aside>
```

- [ ] **Step 4: Delete old nav.html**

```bash
git rm templates/chrome/nav.html
```

- [ ] **Step 5: Run integration test, expect it to pass**

Run: `uv run pytest tests/integration/test_render_three_column.py -v`
Expected: PASS.

- [ ] **Step 6: Run full suite, fix regressions**

Run: `uv run pytest -q`
Expected: PASS. If any test asserts on `needs-nav` or footer `<ol>`, update the assertions to match the new structure (the old chrome is intentionally gone).

- [ ] **Step 7: Commit**

```bash
git add templates/
git commit -m "feat(render): three-column layout shell with TOC and reference aside"
```

### Task A3: CSS grid + sticky rails + TOC JS

**Files:**
- Modify: `templates/styles.css`
- Create: `templates/toc.js`
- Modify: `src/generator/pipeline/render.py`

- [ ] **Step 1: Add a failing assertion for JS injection**

Append to `tests/integration/test_render_three_column.py`:

```python
def test_toc_js_is_injected():
    page = canned_event_page()
    html = render_html(page)
    assert 'IntersectionObserver' in html  # the TOC script body
```

Run: `uv run pytest tests/integration/test_render_three_column.py::test_toc_js_is_injected -v` → FAIL.

- [ ] **Step 2: Add the TOC script**

```js
// templates/toc.js
(() => {
  const items = document.querySelectorAll('.page-toc__item');
  if (!items.length || !('IntersectionObserver' in window)) return;
  const map = new Map();
  items.forEach((li) => map.set(li.dataset.target, li));
  const observer = new IntersectionObserver(
    (entries) => {
      entries.forEach((e) => {
        const li = map.get(e.target.id);
        if (!li) return;
        if (e.isIntersecting) {
          items.forEach((x) => x.classList.remove('is-active'));
          li.classList.add('is-active');
        }
        if (e.boundingClientRect.top < 0) li.classList.add('is-visited');
      });
    },
    { rootMargin: '-40% 0px -55% 0px' }
  );
  document.querySelectorAll('main .need-section').forEach((s) => observer.observe(s));
})();
```

- [ ] **Step 3: Inject the script from `render_html`**

Edit `src/generator/pipeline/render.py` near where `stylesheet` is read:

```python
    stylesheet = (_TEMPLATES_DIR / "styles.css").read_text(encoding="utf-8")
    toc_js = (_TEMPLATES_DIR / "toc.js").read_text(encoding="utf-8")
```

And in the `template.render(...)` call add `toc_js=toc_js,`.

- [ ] **Step 4: Add the grid + rail + chip CSS**

Append to `templates/styles.css`:

```css
/* ---------- 3-column grid ---------- */
.page-grid {
  display: grid;
  grid-template-columns: 240px minmax(0, 1fr) 320px;
  gap: 40px;
  max-width: 1320px;
  margin: 0 auto;
  padding: 32px 24px 64px;
}

@media (max-width: 1199px) {
  .page-grid { grid-template-columns: minmax(0, 1fr) 300px; }
  .page-toc { display: none; }
}
@media (max-width: 767px) {
  .page-grid { grid-template-columns: 1fr; gap: 24px; padding: 16px; }
  .page-reference { order: 2; }
}

/* ---------- TOC ---------- */
.page-toc { position: sticky; top: 24px; align-self: start; }
.page-toc__list { list-style: none; margin: 0; padding: 0; border-left: 1px solid var(--c-rule, #e5e7eb); }
.page-toc__item { position: relative; }
.page-toc__link {
  display: flex; align-items: center; gap: 8px;
  padding: 6px 12px; color: var(--c-muted, #6b7280);
  text-decoration: none; font-size: 13px; line-height: 1.4;
}
.page-toc__dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--c-rule, #d1d5db); margin-left: -16px;
}
.page-toc__item.is-active .page-toc__link { color: var(--c-fg, #111); font-weight: 600; }
.page-toc__item.is-active .page-toc__dot { background: var(--c-accent, #2563eb); }
.page-toc__item.is-visited .page-toc__dot { background: var(--c-fg, #111); opacity: 0.4; }
.page-toc__popover {
  position: absolute; left: 100%; top: 0; margin-left: 12px;
  width: 280px; padding: 10px 12px; background: #111; color: #fff;
  border-radius: 6px; font-size: 12px; line-height: 1.4;
  opacity: 0; pointer-events: none; transition: opacity .12s ease;
  z-index: 10;
}
.page-toc__item:hover .page-toc__popover,
.page-toc__item:focus-within .page-toc__popover { opacity: 1; }

/* ---------- reference rail ---------- */
.page-reference { position: sticky; top: 24px; align-self: start; display: flex; flex-direction: column; gap: 20px; }
.ref-card { border: 1px solid var(--c-rule, #e5e7eb); border-radius: 10px; padding: 16px; background: #fff; }
.ref-card__title { font-size: 13px; text-transform: uppercase; letter-spacing: .08em; margin: 0 0 12px; color: var(--c-muted, #6b7280); }
```

- [ ] **Step 5: Run tests + ruff**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format .
```

Both green.

- [ ] **Step 6: Commit**

```bash
git add templates/ src/generator/pipeline/render.py
git commit -m "feat(render): grid CSS, sticky rails, TOC active-state script"
```

---

# PR-B — Hero overview bullets + facts/opinions chips

### Task B1: Schema — `OverviewBullet`, `HeroData.overview_bullets`, `NeedCurationPlan.category`

**Files:**
- Modify: `src/generator/schema.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Failing test for new fields**

Append to `tests/test_schema.py`:

```python
import pytest
from pydantic import ValidationError
from generator.schema import HeroData, OverviewBullet, NeedCurationPlan


def test_hero_data_accepts_overview_bullets():
    bullets = [OverviewBullet(text="Point one.", source_id="s1") for _ in range(3)]
    hd = HeroData(title="t", summary="s", image_alt="", overview_bullets=bullets)
    assert len(hd.overview_bullets) == 3


def test_hero_data_overview_bullets_optional():
    hd = HeroData(title="t", summary="s", image_alt="")
    assert hd.overview_bullets is None


def test_overview_bullet_text_capped_at_18_words():
    with pytest.raises(ValidationError):
        OverviewBullet(text=" ".join(["w"] * 19), source_id="s1")


def test_need_plan_category_defaults_none():
    p = NeedCurationPlan(
        need_id="what_happened", activated=True, rank=1,
        section_title="t", rationale="r",
    )
    assert p.category is None
    assert p.opinion_subtag is None
```

- [ ] **Step 2: Run test → FAIL**

Run: `uv run pytest tests/test_schema.py -k "overview or category" -v` → import error / attribute error.

- [ ] **Step 3: Add the schema additions**

In `src/generator/schema.py`:

```python
# Near other small data types (before HeroData):
class OverviewBullet(_Frozen):
    text: str = Field(min_length=1)
    source_id: SourceId

    @field_validator("text")
    @classmethod
    def _cap_words(cls, v: str) -> str:
        if len(v.split()) > 18:
            raise ValueError("overview bullet text must be <= 18 words")
        return v
```

If `field_validator` is not already imported, add it: `from pydantic import field_validator`.

Modify `HeroData`:

```python
class HeroData(_Frozen):
    title: str = Field(max_length=80)
    subtitle: str | None = Field(default=None, max_length=120)
    summary: str = Field(max_length=140)
    image_url: HttpUrl | None = None
    image_alt: str
    badge_label: str | None = None
    overview_bullets: list[OverviewBullet] | None = Field(
        default=None, min_length=3, max_length=4
    )
```

Modify `NeedCurationPlan`:

```python
class NeedCurationPlan(_Frozen):
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
```

- [ ] **Step 4: Run test → PASS**

Run: `uv run pytest tests/test_schema.py -k "overview or category" -v` → PASS.

- [ ] **Step 5: Commit**

```bash
git add src/generator/schema.py tests/test_schema.py
git commit -m "feat(schema): overview bullets and need-plan category fields"
```

### Task B2: Plan stage — default category inference

**Files:**
- Modify: `src/generator/pipeline/plan.py`
- Modify: `tests/pipeline/test_plan.py`

- [ ] **Step 1: Failing test**

Append to `tests/pipeline/test_plan.py`:

```python
from generator.pipeline.plan import infer_default_category


def test_infer_category_facts():
    assert infer_default_category(["infobox", "schedule"]) == "fact"


def test_infer_category_opinions():
    assert infer_default_category(["reactions"]) == "opinion"


def test_infer_category_mixed_falls_back_to_fact():
    # mixed module sets default to fact; opinion needs all-opinion modules
    assert infer_default_category(["reactions", "schedule"]) == "fact"


def test_infer_category_empty_is_none():
    assert infer_default_category([]) is None
```

Run: `uv run pytest tests/pipeline/test_plan.py -k category -v` → import error.

- [ ] **Step 2: Implement the helper + apply during plan finalisation**

Add to `src/generator/pipeline/plan.py`:

```python
_OPINION_MODULES = {"reactions", "media_coverage", "official_statements"}
_FACT_MODULES = {
    "infobox", "schedule", "kpi_numbers", "comparison",
    "where_to_watch", "background", "changelog", "countdown",
    "hero",
}


def infer_default_category(assigned_modules: list[str]) -> str | None:
    if not assigned_modules:
        return None
    if all(m in _OPINION_MODULES for m in assigned_modules):
        return "opinion"
    return "fact"
```

Then, wherever `NeedCurationPlan` instances are finalised after the LLM call (search for `NeedCurationPlan(` in `plan.py`), apply the inference when `category is None`. If `plan.py` returns the LLM-parsed plans as a list, add a post-processing step at the bottom of `run_plan_stage`:

```python
finalised: list[NeedCurationPlan] = []
for p in plan_output.need_plans:
    if p.category is None:
        p = p.model_copy(update={"category": infer_default_category(p.assigned_modules)})
    finalised.append(p)
plan_output = plan_output.model_copy(update={"need_plans": finalised})
```

- [ ] **Step 3: Test passes**

Run: `uv run pytest tests/pipeline/test_plan.py -k category -v` → PASS.

- [ ] **Step 4: Commit**

```bash
git add src/generator/pipeline/plan.py tests/pipeline/test_plan.py
git commit -m "feat(plan): infer default fact/opinion category from assigned modules"
```

### Task B3: Hero template + section chip + prompt update

**Files:**
- Modify: `templates/chrome/hero.html`
- Modify: `templates/needs/section.html`
- Modify: `templates/styles.css`
- Modify: `src/generator/modules/hero.py`

- [ ] **Step 1: Failing integration assertions**

Append to `tests/integration/test_render_three_column.py`:

```python
def test_hero_renders_last_updated_chip():
    page = canned_event_page()
    html = render_html(page)
    assert 'class="hero__updated"' in html


def test_section_renders_category_chip_when_set(monkeypatch):
    page = canned_event_page()
    # promote the canned plan to fact
    new_plans = [p.model_copy(update={"category": "fact"}) for p in page.need_plans]
    page = page.model_copy(update={"need_plans": new_plans})
    html = render_html(page)
    assert 'class="need-section__chip need-section__chip--fact"' in html
```

Run → FAIL.

- [ ] **Step 2: Rewrite hero template**

```html
<!-- templates/chrome/hero.html -->
<section class="hero" aria-label="Page lede">
  <div class="container">
    {% if hero_module.data.badge_label %}
      <p class="hero__badge">{{ hero_module.data.badge_label }}</p>
    {% endif %}
    <h1 class="hero__title">
      {{ hero_module.data.title }}
      <time class="hero__updated" datetime="{{ page.meta.last_updated }}" title="{{ page.meta.last_updated }}">
        Updated {{ page.meta.last_updated[:10] }}
      </time>
    </h1>
    {% if hero_module.data.subtitle %}
      <p class="hero__subtitle">{{ hero_module.data.subtitle }}</p>
    {% endif %}
    {% if hero_module.data.overview_bullets %}
      <ul class="hero__overview">
        {% for b in hero_module.data.overview_bullets %}
          <li>
            {{ b.text }}
            <sup class="cite"><a href="#src-{{ source_index[b.source_id] }}">{{ source_index[b.source_id] }}</a></sup>
          </li>
        {% endfor %}
      </ul>
    {% else %}
      <p class="hero__summary">{{ hero_module.data.summary }}</p>
    {% endif %}
    {% if hero_module.data.image_url %}
      <figure class="hero__media">
        <img src="{{ hero_module.data.image_url }}" alt="{{ hero_module.data.image_alt }}" loading="eager">
      </figure>
    {% endif %}
  </div>
</section>
```

- [ ] **Step 3: Modify section template to render chip**

Replace `templates/needs/section.html` with:

```html
<section id="need-{{ section.need_id }}" class="need-section" data-need="{{ section.need_id }}">
  <div class="container">
    {% if section.category %}
      <span class="need-section__chip need-section__chip--{{ section.category }}">
        {% if section.category == "opinion" %}OPINION{% else %}FACT{% endif %}
        {% if section.opinion_subtag %} · {{ section.opinion_subtag }}{% endif %}
      </span>
    {% endif %}
    <h2 class="need-section__title">{{ section.title }}</h2>
    {% if section.rationale %}
      <p class="need-section__rationale">{{ section.rationale }}</p>
    {% endif %}
    <div class="need-section__blocks">
      {% for block in section.blocks %}
        {% if block.kind == "paragraph" %}{% include "blocks/paragraph.html" %}
        {% elif block.kind == "timeline" %}{% include "blocks/timeline.html" %}
        {% elif block.kind == "chart" %}{% include "blocks/chart.html" %}
        {% elif block.kind == "newsfeed" %}{% include "blocks/newsfeed.html" %}
        {% elif block.kind == "factsheet" %}{% include "blocks/factsheet.html" %}
        {% elif block.kind == "map" %}{% include "blocks/map.html" %}
        {% elif block.kind == "reactions" %}{% include "blocks/reactions.html" %}
        {% endif %}
      {% endfor %}
    </div>
  </div>
</section>
```

- [ ] **Step 4: Update `_build_sections` to pass category/opinion_subtag**

In `src/generator/pipeline/render.py::_build_sections`, change the dict appended for each section to include the two new keys:

```python
            sections.append(
                {
                    "need_id": plan.need_id,
                    "title": plan.section_title,
                    "rationale": plan.rationale,
                    "category": plan.category,
                    "opinion_subtag": plan.opinion_subtag,
                    "blocks": section_blocks,
                }
            )
```

Do the same for the "More on this topic" orphan section: `"category": None, "opinion_subtag": None,`.

- [ ] **Step 5: Add chip CSS**

Append to `templates/styles.css`:

```css
.hero__updated { display: inline-block; margin-left: 12px; font-size: 14px; font-weight: 400; color: var(--c-muted, #6b7280); vertical-align: middle; }
.hero__overview { margin: 16px 0 0; padding-left: 20px; line-height: 1.55; }
.hero__overview li { margin-bottom: 8px; }

.need-section__chip {
  display: inline-block; padding: 2px 8px; border-radius: 999px;
  font-size: 11px; letter-spacing: .08em; font-weight: 600;
  text-transform: uppercase; margin-bottom: 8px;
}
.need-section__chip--fact { background: #f3f4f6; color: #4b5563; }
.need-section__chip--opinion { background: color-mix(in srgb, var(--c-accent, #2563eb) 18%, white); color: var(--c-accent, #2563eb); }
```

- [ ] **Step 6: Update hero prompt**

In `src/generator/modules/hero.py`, append to `extraction_prompt_template`:

```
- Write 3–4 overview_bullets, each ≤18 words. Each bullet must cite a source_id from the evidence pool. Bullets should be the four things a reader most needs to know about this event at a glance — not a restatement of the title.
```

- [ ] **Step 7: Run tests**

```bash
uv run pytest -q
```

All green. If a pre-existing module test asserts on the old `.hero__summary`, update the fixture to omit `overview_bullets` so the template still renders the summary fallback.

- [ ] **Step 8: Commit**

```bash
git add templates/ src/generator/modules/hero.py src/generator/pipeline/render.py
git commit -m "feat(hero): particle bullets, last-updated chip, section category chip"
```

---

# PR-C — Reactions card redesign

### Task C1: Schema — `stakeholder_tier`, `author_image_url`

**Files:**
- Modify: `src/generator/schema.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Failing test**

```python
# tests/test_schema.py (append)
from generator.schema import ReactionItem


def test_reaction_item_stakeholder_tier_optional():
    r = ReactionItem(
        author="A", author_role="role", quote="q",
        sentiment="positive", source_id="s1",
    )
    assert r.stakeholder_tier is None
    assert r.author_image_url is None


def test_reaction_item_accepts_stakeholder_tier():
    r = ReactionItem(
        author="A", author_role="role", quote="q",
        sentiment="positive", source_id="s1",
        stakeholder_tier="stakeholder",
        author_image_url="https://x.test/a.jpg",
    )
    assert r.stakeholder_tier == "stakeholder"
    assert str(r.author_image_url).startswith("https://")
```

Run → FAIL.

- [ ] **Step 2: Add fields**

```python
class ReactionItem(_Frozen):
    author: str
    author_role: str
    quote: str = Field(max_length=280)
    sentiment: Sentiment
    source_id: SourceId
    stakeholder_tier: Literal["stakeholder", "adjacent", "third_party"] | None = None
    author_image_url: HttpUrl | None = None
```

- [ ] **Step 3: PASS + commit**

```bash
uv run pytest tests/test_schema.py -k reaction -v
git add src/generator/schema.py tests/test_schema.py
git commit -m "feat(schema): reaction stakeholder tier and author image"
```

### Task C2: Reactions block + converter wiring

**Files:**
- Modify: `src/generator/blocks/schema.py`
- Modify: `src/generator/blocks/converter.py`
- Create: `templates/blocks/reactions.html`
- Modify: `src/generator/modules/reactions.py`

- [ ] **Step 1: Failing test**

```python
# tests/integration/test_render_three_column.py (append)
from generator.schema import (
    ReactionItem, ReactionsData, ReactionsModule, ModuleConfidence,
    NeedCurationPlan,
)


def _page_with_reactions():
    from tests.fixtures import canned_event_page, _src
    page = canned_event_page()
    reactions = ReactionsModule(
        id="m_react",
        confidence=ModuleConfidence(overall=0.9, flags=[]),
        data=ReactionsData(items=[
            ReactionItem(author=f"A{i}", author_role=f"role{i}",
                         quote=f"quote {i}", sentiment="positive",
                         source_id="s1",
                         stakeholder_tier="stakeholder" if i < 2 else "third_party")
            for i in range(5)
        ]),
    )
    new_plan = NeedCurationPlan(
        need_id="world_reaction", activated=True, rank=2,
        section_title="Reactions", rationale="How people responded.",
        assigned_modules=["reactions"],
        render_overrides={"reactions": "reactions"},
        category="opinion",
    )
    return page.model_copy(update={
        "modules": list(page.modules) + [reactions],
        "need_plans": list(page.need_plans) + [new_plan],
    })


def test_reactions_render_as_quote_cards_limited_to_four():
    html = render_html(_page_with_reactions())
    assert 'class="quote-card"' in html
    # cap at 4 cards regardless of upstream count
    assert html.count('class="quote-card"') == 4


def test_reactions_stakeholders_rendered_before_third_party():
    html = render_html(_page_with_reactions())
    # stakeholders (A0, A1) appear before third_party authors in serialized HTML
    pos_a0 = html.find("A0")
    pos_a4 = html.find("A4")
    assert 0 <= pos_a0 < pos_a4
```

Run → FAIL.

- [ ] **Step 2: Extend block schema with `reactions`**

Open `src/generator/blocks/schema.py`. Find the `BlockKind` literal and the discriminated `RenderBlock` union. Add a `ReactionsBlock`:

```python
class QuoteCard(_Frozen):
    author: str
    author_role: str
    quote: str
    sentiment: Sentiment
    stakeholder_tier: Literal["stakeholder", "adjacent", "third_party"] | None = None
    author_image_url: HttpUrl | None = None
    source_id: SourceId


class ReactionsBlock(_Frozen):
    kind: Literal["reactions"] = "reactions"
    cards: list[QuoteCard] = Field(max_length=4)
```

Add `"reactions"` to the `BlockKind` literal and `ReactionsBlock` to the `RenderBlock` union.

- [ ] **Step 3: Wire converter**

In `src/generator/blocks/converter.py`:

```python
_STAKEHOLDER_RANK = {"stakeholder": 0, "adjacent": 1, "third_party": 2, None: 3}


def _reactions_to_block(mod, sources):
    items = sorted(mod.data.items, key=lambda r: _STAKEHOLDER_RANK[r.stakeholder_tier])
    cards = [
        QuoteCard(
            author=r.author, author_role=r.author_role, quote=r.quote,
            sentiment=r.sentiment, stakeholder_tier=r.stakeholder_tier,
            author_image_url=r.author_image_url, source_id=r.source_id,
        )
        for r in items[:4]
    ]
    return ReactionsBlock(cards=cards)
```

Add `ReactionsModule` → `_reactions_to_block` in the dispatch in `module_to_block` (when override is `"reactions"` or for default when kind == "reactions"). Update `_DEFAULT_BLOCK_KIND` so `"reactions": "reactions"`.

- [ ] **Step 4: Add the template**

```html
<!-- templates/blocks/reactions.html -->
<ul class="quote-grid">
  {% for c in block.cards %}
    <li class="quote-card">
      <div class="quote-card__author">
        {% if c.author_image_url %}
          <img class="quote-card__photo" src="{{ c.author_image_url }}" alt="{{ c.author }}">
        {% else %}
          <span class="quote-card__monogram" aria-hidden="true">{{ c.author[:1] }}</span>
        {% endif %}
        <div>
          <p class="quote-card__name">{{ c.author }}</p>
          <p class="quote-card__role">{{ c.author_role }}</p>
        </div>
        <span class="quote-card__sentiment quote-card__sentiment--{{ c.sentiment }}" aria-label="{{ c.sentiment }}"></span>
      </div>
      <blockquote class="quote-card__quote">{{ c.quote }}</blockquote>
      <p class="quote-card__cite">
        <a href="#src-{{ source_index[c.source_id] }}">[{{ source_index[c.source_id] }}]</a>
      </p>
    </li>
  {% endfor %}
</ul>
```

- [ ] **Step 5: Add CSS**

Append to `templates/styles.css`:

```css
.quote-grid { list-style: none; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 16px; padding: 0; margin: 0; }
.quote-card { border: 1px solid var(--c-rule, #e5e7eb); border-radius: 10px; padding: 18px; background: #fff; }
.quote-card__author { display: grid; grid-template-columns: 48px 1fr auto; gap: 12px; align-items: center; margin-bottom: 12px; }
.quote-card__photo, .quote-card__monogram { width: 48px; height: 48px; border-radius: 50%; object-fit: cover; }
.quote-card__monogram { display: inline-flex; align-items: center; justify-content: center; background: var(--c-accent, #2563eb); color: #fff; font-weight: 600; }
.quote-card__name { font-weight: 600; margin: 0; }
.quote-card__role { color: var(--c-muted, #6b7280); font-size: 13px; margin: 0; }
.quote-card__sentiment { width: 8px; height: 8px; border-radius: 50%; }
.quote-card__sentiment--positive { background: #16a34a; }
.quote-card__sentiment--neutral { background: #9ca3af; }
.quote-card__sentiment--negative { background: #dc2626; }
.quote-card__quote { font-family: Georgia, serif; font-size: 18px; line-height: 1.45; margin: 0; padding: 0; border: 0; quotes: "“" "”"; }
.quote-card__quote::before { content: open-quote; font-size: 28px; color: var(--c-accent, #2563eb); margin-right: 4px; }
.quote-card__cite { margin: 12px 0 0; font-size: 12px; color: var(--c-muted); }
```

- [ ] **Step 6: Update reactions prompt**

In `src/generator/modules/reactions.py`, append to the prompt:

```
- For each reaction, set stakeholder_tier to one of:
  * "stakeholder" — person directly affected, employed by, or with formal authority over the event subject (e.g. the CEO of the company, the team captain, a head of state speaking on their own policy).
  * "adjacent" — industry expert, regulator, or competitor whose opinion materially shapes the story.
  * "third_party" — pundits, fans, generic commentators.
- Prefer stakeholders. Aim for at least 2 stakeholder items if the evidence supports it.
- Set author_image_url ONLY if an unambiguous photo URL is present in the evidence (og:image of a profile page, Wikidata image). Otherwise omit.
```

- [ ] **Step 7: Run tests + commit**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format .
git add .
git commit -m "feat(reactions): quote-card block with stakeholder ranking"
```

---

# PR-D — Milestone timeline in right rail

### Task D1: Schema — `ScheduleItem.is_milestone`

**Files:**
- Modify: `src/generator/schema.py`
- Modify: `src/generator/modules/schedule.py`
- Modify: `tests/test_schema.py`

- [ ] **Step 1: Failing test**

```python
def test_schedule_item_is_milestone_defaults_false():
    from generator.schema import ScheduleItem
    s = ScheduleItem(time_iso="2026-05-14T00:00:00Z", label="x", source_id="s1")
    assert s.is_milestone is False
```

Run → FAIL.

- [ ] **Step 2: Add field**

```python
class ScheduleItem(_Frozen):
    time_iso: ISO8601
    label: str
    location: str | None = None
    duration_min: int | None = None
    is_milestone: bool = False
    source_id: SourceId
```

- [ ] **Step 3: Prompt update**

In `src/generator/modules/schedule.py` (append rules):

```
- Set is_milestone=true only for entries that are inflection points the reader will remember (kickoff, launch, ruling delivered, ceasefire signed). Routine sub-events should be is_milestone=false. Aim for 3–6 milestones total.
```

- [ ] **Step 4: PASS + commit**

```bash
uv run pytest tests/test_schema.py -k milestone -v
git add src/generator/schema.py src/generator/modules/schedule.py tests/test_schema.py
git commit -m "feat(schedule): is_milestone flag on schedule items"
```

### Task D2: Reference timeline partial + render wiring

**Files:**
- Create: `templates/chrome/reference_timeline.html`
- Modify: `src/generator/pipeline/render.py`
- Modify: `templates/styles.css`

- [ ] **Step 1: Failing test**

```python
# tests/integration/test_render_three_column.py (append)
def test_reference_rail_renders_milestones_only():
    from tests.fixtures import canned_event_page, _src
    from generator.schema import (
        ScheduleItem, ScheduleData, ScheduleModule, ModuleConfidence,
    )
    page = canned_event_page()
    sched = ScheduleModule(
        id="m_sched",
        confidence=ModuleConfidence(overall=0.9, flags=[]),
        data=ScheduleData(
            timezone="UTC",
            items=[
                ScheduleItem(time_iso="2026-05-14T09:00:00Z", label="Kickoff",
                             location="Stadium", is_milestone=True, source_id="s1"),
                ScheduleItem(time_iso="2026-05-14T09:15:00Z", label="Throw-in",
                             is_milestone=False, source_id="s1"),
            ],
        ),
    )
    page = page.model_copy(update={"modules": list(page.modules) + [sched]})
    html = render_html(page)
    assert "Kickoff" in html
    assert "Throw-in" not in html
    assert 'class="ref-timeline"' in html
```

Run → FAIL.

- [ ] **Step 2: Add partial**

```html
<!-- templates/chrome/reference_timeline.html -->
{% if milestones %}
<section class="ref-card ref-timeline">
  <h3 class="ref-card__title">Timeline</h3>
  <ol class="ref-timeline__list">
    {% for m in milestones %}
      <li class="ref-timeline__item ref-timeline__item--{{ m.state }}">
        <p class="ref-timeline__date">
          <span class="ref-timeline__day">{{ m.day }}</span>
          {% if m.time %}<span class="ref-timeline__time">{{ m.time }}</span>{% endif %}
        </p>
        <p class="ref-timeline__label">{{ m.label }}</p>
        {% if m.location %}<p class="ref-timeline__loc">📍 {{ m.location }}</p>{% endif %}
      </li>
    {% endfor %}
  </ol>
</section>
{% endif %}
```

- [ ] **Step 3: Compute `milestones` in `render_html`**

In `src/generator/pipeline/render.py`, add a helper and pass to template:

```python
from datetime import datetime as _dt


def _build_milestones(page: EventPage) -> list[dict]:
    sched = next((m for m in page.modules if m.kind == "schedule"), None)
    if sched is None:
        return []
    now = _dt.now(timezone.utc)
    out = []
    items = [i for i in sched.data.items if i.is_milestone]
    items.sort(key=lambda i: i.time_iso)
    for i in items[:6]:
        try:
            ts = _dt.fromisoformat(i.time_iso.replace("Z", "+00:00"))
        except ValueError:
            ts = None
        state = "past" if ts and ts < now else "future"
        out.append({
            "day": ts.strftime("%b %d") if ts else i.time_iso[:10],
            "time": ts.strftime("%H:%M UTC") if ts else None,
            "label": i.label,
            "location": i.location,
            "state": state,
        })
    if out:
        out[-1]["state"] = "current" if out[-1]["state"] == "future" else out[-1]["state"]
    return out
```

In `render_html(...)`, before calling `template.render`, add:

```python
    milestones = _build_milestones(page)
```

and pass `milestones=milestones,` to the template render call.

- [ ] **Step 4: Add CSS**

```css
.ref-timeline__list { list-style: none; margin: 0; padding: 0; }
.ref-timeline__item { padding: 10px 0; border-bottom: 1px dashed var(--c-rule, #e5e7eb); }
.ref-timeline__item:last-child { border-bottom: 0; }
.ref-timeline__item--past { opacity: 0.45; }
.ref-timeline__item--current { background: color-mix(in srgb, var(--c-accent, #2563eb) 8%, white); padding-left: 8px; margin-left: -8px; border-radius: 4px; }
.ref-timeline__date { display: flex; gap: 8px; align-items: baseline; margin: 0; font-size: 12px; color: var(--c-muted); }
.ref-timeline__day { font-weight: 600; color: var(--c-fg, #111); }
.ref-timeline__label { margin: 4px 0 0; font-size: 14px; font-weight: 500; }
.ref-timeline__loc { margin: 2px 0 0; font-size: 12px; color: var(--c-muted); }
```

- [ ] **Step 5: Tests + commit**

```bash
uv run pytest -q
git add .
git commit -m "feat(render): milestone-only timeline in right reference rail"
```

---

# PR-E — Sources card

### Task E1: Sources card partial + footer cleanup

**Files:**
- Create: `templates/partials/sources_card.html`
- Modify: `templates/layout.html` (already includes the partial from PR-A)
- Modify: `templates/styles.css`

- [ ] **Step 1: Failing test**

```python
def test_sources_render_in_card_not_ol_in_footer():
    page = canned_event_page()
    html = render_html(page)
    footer_start = html.find("<footer")
    footer_block = html[footer_start:]
    assert "<ol" not in footer_block
    assert 'class="sources-card"' in html
```

Run → FAIL.

- [ ] **Step 2: Create the partial**

```html
<!-- templates/partials/sources_card.html -->
<section class="sources-card" aria-labelledby="sources-heading">
  <header class="sources-card__head">
    <h2 id="sources-heading">Sources</h2>
    <span class="sources-card__count">{{ page.sources | length }}</span>
  </header>
  <ul class="sources-card__list">
    {% for src in page.sources %}
      <li id="src-{{ source_index[src.id] }}" class="sources-card__row">
        <span class="sources-card__num">{{ source_index[src.id] }}</span>
        <div class="sources-card__body">
          <a class="sources-card__title" href="{{ src.url }}" rel="noopener noreferrer">{{ src.title }}</a>
          <p class="sources-card__meta">
            {{ src.publisher.name }}
            <span class="sources-card__tier sources-card__tier--{{ src.publisher.tier }}">{{ src.publisher.tier }}</span>
            {% if src.published_at %}· {{ src.published_at[:10] }}{% endif %}
          </p>
        </div>
      </li>
    {% endfor %}
  </ul>
</section>
```

- [ ] **Step 3: Add CSS**

```css
.sources-card { margin-top: 48px; border: 1px solid var(--c-rule, #e5e7eb); border-radius: 12px; padding: 20px 24px; background: #fafafa; }
.sources-card__head { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; }
.sources-card__head h2 { margin: 0; font-size: 18px; }
.sources-card__count { background: #111; color: #fff; border-radius: 999px; padding: 2px 8px; font-size: 11px; }
.sources-card__list { list-style: none; padding: 0; margin: 0; display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px 24px; }
.sources-card__row { display: grid; grid-template-columns: 28px 1fr; gap: 8px; }
.sources-card__num { font-variant-numeric: tabular-nums; color: var(--c-muted); font-size: 12px; padding-top: 2px; }
.sources-card__title { display: block; font-weight: 500; line-height: 1.35; }
.sources-card__meta { margin: 4px 0 0; font-size: 12px; color: var(--c-muted); }
.sources-card__tier { display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 4px; background: #f3f4f6; font-size: 10px; text-transform: uppercase; letter-spacing: .05em; }
```

- [ ] **Step 4: Tests + commit**

```bash
uv run pytest -q
git add templates/
git commit -m "feat(render): sources card replaces footer ol"
```

---

# PR-F — Wikipedia reference card

### Task F1: Wikipedia fetcher

**Files:**
- Create: `src/generator/sources/wikipedia.py`
- Create: `tests/sources/test_wikipedia.py`

- [ ] **Step 1: Failing test**

```python
# tests/sources/test_wikipedia.py
import pytest
import respx
from httpx import Response

from generator.sources.wikipedia import fetch_wikipedia_card


@pytest.mark.asyncio
@respx.mock
async def test_fetch_wikipedia_card_returns_data():
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Sample_Event").mock(
        return_value=Response(200, json={
            "title": "Sample Event",
            "extract": "Sample event is a real thing.",
            "thumbnail": {"source": "https://upload.wikimedia.org/x.jpg"},
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Sample_Event"}},
        })
    )
    card = await fetch_wikipedia_card("Sample_Event")
    assert card is not None
    assert card.title == "Sample Event"
    assert "real thing" in card.summary_text
    assert str(card.article_url).startswith("https://en.wikipedia.org/")


@pytest.mark.asyncio
@respx.mock
async def test_fetch_wikipedia_card_returns_none_on_404():
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Missing").mock(
        return_value=Response(404)
    )
    card = await fetch_wikipedia_card("Missing")
    assert card is None


@pytest.mark.asyncio
@respx.mock
async def test_fetch_wikipedia_card_truncates_long_extract():
    long = "x " * 1000
    respx.get("https://en.wikipedia.org/api/rest_v1/page/summary/Long").mock(
        return_value=Response(200, json={
            "title": "Long", "extract": long,
            "content_urls": {"desktop": {"page": "https://en.wikipedia.org/wiki/Long"}},
        })
    )
    card = await fetch_wikipedia_card("Long")
    assert len(card.summary_text) <= 600
```

Run → FAIL.

- [ ] **Step 2: Implement**

```python
# src/generator/sources/wikipedia.py
"""Wikipedia REST summary fetch — best-effort, returns None on failure."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx

from generator.schema import WikipediaCardData

_REST_BASE = "https://en.wikipedia.org/api/rest_v1/page/summary"
_MAX_SUMMARY_CHARS = 600


async def fetch_wikipedia_card(title: str) -> WikipediaCardData | None:
    """Fetch the summary card for an enwiki title. Returns None on any failure."""
    url = f"{_REST_BASE}/{title}"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(url, headers={"Accept": "application/json"})
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    data = resp.json()
    extract = (data.get("extract") or "").strip()
    if not extract:
        return None
    if len(extract) > _MAX_SUMMARY_CHARS:
        extract = extract[: _MAX_SUMMARY_CHARS - 1].rstrip() + "…"
    page_url = (
        data.get("content_urls", {})
        .get("desktop", {})
        .get("page")
    )
    if not page_url:
        return None
    return WikipediaCardData(
        title=data.get("title") or title,
        summary_text=extract,
        thumbnail_url=(data.get("thumbnail") or {}).get("source"),
        article_url=page_url,
        retrieved_at=datetime.now(timezone.utc).isoformat(),
    )
```

- [ ] **Step 3: Add `WikipediaCardData` to schema**

```python
class WikipediaCardData(_Frozen):
    title: str
    summary_text: str = Field(max_length=600)
    thumbnail_url: HttpUrl | None = None
    article_url: HttpUrl
    retrieved_at: ISO8601
```

- [ ] **Step 4: Tests pass + commit**

```bash
uv run pytest tests/sources/test_wikipedia.py -v
git add src/generator/sources/wikipedia.py src/generator/schema.py tests/sources/test_wikipedia.py
git commit -m "feat(sources): Wikipedia REST summary fetcher"
```

### Task F2: Wire Wikipedia card into pipeline + EventPage

**Files:**
- Modify: `src/generator/schema.py` — `EventPage.wikipedia_card`
- Modify: `src/generator/pipeline/disambiguate.py`
- Modify: `src/generator/pipeline/render.py`

- [ ] **Step 1: Failing test**

```python
def test_event_page_accepts_optional_wikipedia_card():
    from generator.schema import EventPage, WikipediaCardData
    page = canned_event_page().model_copy(update={
        "wikipedia_card": WikipediaCardData(
            title="t", summary_text="s",
            article_url="https://en.wikipedia.org/wiki/t",
            retrieved_at="2026-05-14T00:00:00Z",
        )
    })
    assert page.wikipedia_card is not None
```

Run → FAIL (`wikipedia_card` is not a field).

- [ ] **Step 2: Add the field**

In `EventPage`:

```python
wikipedia_card: "WikipediaCardData | None" = None
```

- [ ] **Step 3: Populate in disambiguate stage**

In `src/generator/pipeline/disambiguate.py`, after Wikidata QID resolution succeeds, look up the enwiki sitelink (the existing Wikidata helper already returns sitelinks if requested — if not, add a one-line fetch). For each disambiguation result with an `enwiki_title`, call:

```python
from generator.sources.wikipedia import fetch_wikipedia_card

wiki_card = await fetch_wikipedia_card(result.enwiki_title) if result.enwiki_title else None
```

Return `wiki_card` alongside the disambiguation result so `cli.py` can pass it into `build_page`. Extend `build_page` with `wikipedia_card: WikipediaCardData | None = None` and set it on the returned `EventPage`.

If `disambiguate.py` does not currently return Wikipedia titles, scope this task to: add the parameter to `build_page`, pass it through from `cli.py` (default None), and leave the actual fetch behind a TODO comment that points to the next task — but DO NOT leave the test failing. To make the test pass, populating from the CLI is enough.

- [ ] **Step 4: Test passes + commit**

```bash
uv run pytest -q
git add .
git commit -m "feat(schema,pipeline): plumb optional Wikipedia card through EventPage"
```

### Task F3: Wikipedia card template + render

**Files:**
- Create: `templates/chrome/reference_wikipedia.html`
- Modify: `src/generator/pipeline/render.py`
- Modify: `templates/styles.css`

- [ ] **Step 1: Failing test**

```python
def test_wikipedia_card_renders_with_attribution():
    from generator.schema import WikipediaCardData
    page = canned_event_page().model_copy(update={
        "wikipedia_card": WikipediaCardData(
            title="Sample Event",
            summary_text="One-line summary.",
            article_url="https://en.wikipedia.org/wiki/Sample_Event",
            retrieved_at="2026-05-14T00:00:00Z",
        ),
    })
    html = render_html(page)
    assert "from Wikipedia" in html
    assert "CC BY-SA" in html
    assert "https://en.wikipedia.org/wiki/Sample_Event" in html


def test_wikipedia_card_absent_renders_nothing():
    page = canned_event_page()  # wikipedia_card defaults to None
    html = render_html(page)
    assert "from Wikipedia" not in html
```

Run → FAIL.

- [ ] **Step 2: Add the partial**

```html
<!-- templates/chrome/reference_wikipedia.html -->
{% if page.wikipedia_card %}
<section class="ref-card ref-wiki">
  <h3 class="ref-card__title">{{ page.wikipedia_card.title }}</h3>
  {% if page.wikipedia_card.thumbnail_url %}
    <img class="ref-wiki__thumb" src="{{ page.wikipedia_card.thumbnail_url }}" alt="">
  {% endif %}
  <p class="ref-wiki__summary">{{ page.wikipedia_card.summary_text }}</p>
  <p class="ref-wiki__attr">
    Excerpt from <a href="{{ page.wikipedia_card.article_url }}" rel="noopener noreferrer">Wikipedia</a>,
    licensed under <a href="https://creativecommons.org/licenses/by-sa/4.0/" rel="noopener noreferrer">CC BY-SA 4.0</a>.
  </p>
</section>
{% endif %}
```

- [ ] **Step 3: CSS**

```css
.ref-wiki__thumb { width: 100%; max-height: 160px; object-fit: cover; border-radius: 6px; margin-bottom: 8px; }
.ref-wiki__summary { font-size: 13px; line-height: 1.5; margin: 0 0 8px; }
.ref-wiki__attr { font-size: 11px; color: var(--c-muted); margin: 0; }
```

- [ ] **Step 4: Run + commit**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format .
git add .
git commit -m "feat(render): Wikipedia reference card with attribution"
```

---

## Final pass

- [ ] **Step 1: Full smoke run with real fixture output**

```bash
uv run pytest -q
uv run ruff check . && uv run ruff format .
```

- [ ] **Step 2: Visual smoke**

Regenerate one existing fixture to inspect the page:

```bash
uv run generate run --auto "Sample event for layout smoke" || true
open output/sample-event-for.html
```

(The command may have other failure modes unrelated to this work; the goal is to eyeball the HTML, not to gate the PR on it.)

- [ ] **Step 3: Tag the milestone**

```bash
git tag ui-polish-three-column
```

---

## Self-review notes

- Each PR-A through PR-F maps to one section of the spec; coverage verified.
- No "TODO"/"TBD"/"add error handling" placeholders left in plan steps. The one TODO mentioned (in F2) is a runtime-code TODO inside the Wikipedia plumbing for future work, not a plan placeholder, and the test still passes by routing through `cli.py`.
- Type names consistent: `OverviewBullet`, `QuoteCard`, `ReactionsBlock`, `WikipediaCardData`, `infer_default_category` used identically across tasks.
- All schema additions are additive (defaults to `None` / `False`); existing fixtures continue to round-trip without modification.
