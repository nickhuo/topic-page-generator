"""Needs-driven plan prompt — produces NeedPlanOutput.

Replaces the deterministic archetype_table lookup. The LLM decides, for each
of the 8 reader needs:
  - activated: does this need have substance to talk about for this event?
  - rank: in what reading order?
  - section_title: event-specific H2 (NOT the literal need name)
  - rationale: why this need matters here (or why it doesn't)
  - fetch_queries: 1-2 Tavily search prompts for this need's evidence
  - assigned_modules: which module kinds belong under this need
  - publisher_quota: minimum source counts per tier for this need's evidence
"""

from __future__ import annotations

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import DisambiguationOutput, TriageOutput

_NEED_BRIEFS = """\
The 8 reader needs (NeedId values). For each one you must decide activation:

- what_happened     — what is this / what happened. Almost always activated.
- when_where        — date, place, time. Activated when event has a clear time/place.
- who_involved      — key parties, actors, teams, organizations.
- current_state     — what is happening right now (live state, latest news).
- why_matters       — significance, context, stakes.
- world_reaction    — what fans / critics / pundits / public are saying.
- what_can_do       — actionable: where to watch, tickets, sign up, official site.
- what_next         — what comes next: future schedule, milestones, predictions.
"""

_MODULE_CATALOG = """\
Available module kinds (assigned_modules takes from this list):

  hero            — page-top identity (title + image + summary)
  infobox         — key-value facts table (when, where, who, etc.)
  schedule        — chronological list of events/games/dates
  kpi_numbers     — 1-4 numeric tiles (price, viewers, sales)
  comparison      — 2-3 subjects compared across axes
  changelog       — versioned changes (product/feature releases)
  reactions       — quotes from public/fans (5-15 items). The page renders
                    these as Perspectives tabs grouped by `sentiment`; cards
                    must span at least two sentiments (positive / neutral /
                    negative) so multiple tabs appear.
  media_coverage  — headline list with publisher attribution
  official_statements — quotes from authoritative roles
  where_to_watch  — TV / streaming / in-person channels
  background     — 1-2 explainer paragraphs

A single module can serve multiple needs. The same need can host multiple
modules. Hero usually goes under what_happened and is required.
"""

_INSTRUCTIONS = """\
TASK: Curate this event page as a senior news editor.

For each of the 8 reader needs, decide whether the page should surface it,
in what rank order, with what section title, and (when activated) what
search queries and which modules belong inside it. Output `NeedPlanOutput`.

OUTPUT REQUIREMENTS — read carefully:

1. need_plans MUST contain all 8 needs (one entry per NeedId). Use
   activated=false to suppress a need from the page; do not omit it.

2. ranks MUST be a permutation of 1..8 across the 8 plans (no duplicates,
   no gaps). Activated needs naturally sort to the top by rank ascending,
   but rank is also assigned to inactive ones for editor override.

3. section_title MUST be event-specific. Not "How is the world reacting?"
   but "How fans and broadcasters are reacting to the 2026 World Cup".
   Write like a magazine subhead: concrete, specific, declarative.

4. rationale is 1 short sentence explaining why this need is/isn't on the
   page for THIS event. The editor sees this and can override.

5. fetch_queries (for activated needs only): give 1-2 queries, each with a
   focused angle. Examples:
   - world_reaction → "world cup 2026 fan reactions commentary critics"
     (angle: commentary)
   - where_to_watch → "world cup 2026 broadcast streaming rights"
     (angle: official)
   - current_state → "world cup 2026 qualifying news recent" (time_range_days: 14)
   Each query should be self-sufficient (Tavily will search the web with it).

6. assigned_modules: pick 1-3 module kinds from the catalog per activated need.
   Don't double-assign a module to multiple needs; pick the one it serves best.

7. publisher_quota: a soft floor. For world_reaction, expect at least 2 T1
   independent voices; for what_can_do, expect 1 T0 official source. Use 0
   for tiers that aren't needed.

8. layout_preset_id: pick one of `live_dominance` / `product_focus` /
   `imminent_event` / `reference` based on temporal posture and event type.
"""


def build_need_plan_messages(
    triage: TriageOutput, disamb: DisambiguationOutput
) -> list[dict]:
    chosen_entity = (
        disamb.chosen.entity if disamb.chosen else triage.primary_entity or "Unknown"
    )
    chosen_type = (
        disamb.chosen.event_type_hint
        if disamb.chosen
        else triage.event_type_hint or "generic"
    )
    time_anchor = disamb.chosen.time_anchor if disamb.chosen else triage.time_anchor
    payload = (
        f"EVENT: {chosen_entity}\n"
        f"EVENT_TYPE_HINT: {chosen_type}\n"
        f"TEMPORAL_POSTURE: {triage.temporal_posture}\n"
        f"TIME_ANCHOR: {time_anchor or 'unknown'}\n\n"
        f"TRIAGE_REASONING: {triage.reasoning}\n\n"
        "OUTPUT a NeedPlanOutput now."
    )
    system = (
        BASE_PREAMBLE
        + "\n\n"
        + _NEED_BRIEFS
        + "\n"
        + _MODULE_CATALOG
        + "\n"
        + _INSTRUCTIONS
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": payload},
    ]
