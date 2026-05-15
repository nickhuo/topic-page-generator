# Design System v2

## Files changed

| File | What changed |
|------|-------------|
| `styles.css` | Full rewrite — new design tokens, 2-col layout, all component styles |
| `layout.html` | 2-col grid (main + sidebar), Google Fonts, no 3-col |
| `toc.js` | Horizontal nav scroll spy + Perspectives tab switching |
| `chrome/hero.html` | `hero__inner` max-width wrapper, new bullet list style |
| `chrome/toc.html` | Left sidebar TOC → horizontal sticky nav chips |
| `chrome/reference.html` | Sidebar container (timeline + wikipedia) |
| `chrome/reference_timeline.html` | Compact timeline, no emoji |
| `chrome/reference_wikipedia.html` | Background card with excerpt + link |
| `needs/section.html` | Rationale hidden, unified chip (no color variants) |
| `blocks/paragraph.html` | Cleaner inline citation style |
| `blocks/newsfeed.html` | Serif headline, outlet name, cleaner card |
| `blocks/reactions.html` | Perspectives tab layout (Optimistic / Critical / Analytical) |
| `blocks/timeline_sidebar.html` | Sidebar-only timeline (main-column timeline removed) |

## Files unchanged (copied as-is)

| File | Notes |
|------|-------|
| `blocks/chart.html` | No structural change; styles updated via styles.css |

## Files removed

- `templates/partials/sources_card.html` — sources card at page bottom removed per design decision
- `templates/chrome/toc.html` replaced (left sidebar TOC no longer used)
- `templates/blocks/{factsheet,map}.html` — block kinds removed entirely
- `templates/blocks/timeline.html` — main-column timeline removed; timelines render in the sidebar only

## Design decisions

- **Palette variables**: The pipeline injects `--color-ink`, `--color-bg`, etc. These are mapped to
  `--ink`, `--bg`, etc. in styles.css via `var()`. Palette customisation still works.
- **Rationale hidden**: `section.rationale` is no longer rendered in the page. It remains in the
  data for editor tooling but readers don't see it.
- **Chip colours removed**: All section chips use a single neutral grey style. Category
  distinction (fact/opinion) is still in the HTML class for scripting if needed.
- **Reactions → Perspectives tabs**: `block.cards` items grouped by `sentiment` field.
  Positive → "Optimistic", Negative → "Critical", Neutral → "Analytical".
  Empty groups are omitted automatically.
- **Citations**: Still numbered `[1]` — favicon approach requires pipeline changes
  (expose `source.publisher.domain` or use `urlparse` Jinja2 filter).
