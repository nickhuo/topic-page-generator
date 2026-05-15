"""Prompt builder for the curation planner.

One LLM call. Input: triage facts + canonical title + the 6 backbone sections
already chosen. Output: 0–4 SectionPlan objects with `kind="curated"`.

The curation planner is a one-shot — there is no refinement loop. It picks
the few extra sections that make THIS specific event richer than the generic
backbone alone could.
"""

from __future__ import annotations

import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import EventFacts, SectionPlan

_BLOCK_KIND_CATALOG = """\
Block kinds you can choose for each curated section (closed enum):

- paragraph: prose or bullet text. Use for narrative, analysis, explainer.
- timeline: ordered milestone entries. Use only if NOT already covered by the backbone timeline.
- chart: stat callouts, bar series, or compare tables. Use for quantitative payloads.
- newsfeed: external link cards. Use for "where to watch", "channels", "quote roundup".
- factsheet: labeled key/value rows. Use for cast lists, lineups, KPI tables.
- map: geocoded locations. Use only when geography is load-bearing.
- reactions: 2–4 quote cards spanning multiple sentiments or stakeholder tiers.
"""

_INSTRUCTIONS = """\
You are the curation planner. The backbone planner has already chosen six
always-on sections (listed under "ALREADY CHOSEN"). Your job: decide which
0 to 4 additional sections would make THIS event meaningfully richer.

Rules:
1. Output between 0 and 4 curated sections. Fewer is fine. Zero is fine.
2. Never duplicate or paraphrase a backbone section. If `overview` already
   covers context, don't add another paragraph called "Context".
3. Each curated section must pass a "would the reader miss it?" test. If you
   can't articulate the unique value in one sentence, skip it.
4. `section_id` is a free-form snake_case slug (e.g. "kpi_dashboard",
   "people_relationships", "where_to_watch"). It must NOT collide with any
   BackboneSectionId.
5. `kind` must be `"curated"`.
6. `rank` starts at 7 (after the 6 backbone ranks) and increments. No gaps.
7. `block_kind` must be one of the 7 closed-enum kinds above.
8. `intent`: one sentence describing what the section answers and how.
9. `acceptance.description`: one sentence describing what success looks like.
   Set `min_sources` and `min_publishers` honestly — a niche curated section
   often needs only 1 source, a reactions block needs ≥2 distinct sentiments.

Triage hints for picking sections:
- Sports / live event: consider "where_to_watch" (newsfeed variant=channels)
  or a "lineup" (factsheet).
- Product launch / earnings: consider "kpi_dashboard" (chart, stat or bar).
- Geopolitical / disaster: consider a map.
- Polarizing / contested: consider a reactions section spanning sentiments.
- Comparative (rival product, prior cycle): consider a chart compare_table.

Strict output: a SectionPlanOutput JSON object with a `sections` list (0–4
items). Do NOT include the backbone sections in your output — only your
additions.
"""


def build_curation_messages(
    facts: EventFacts,
    canonical_title: str,
    backbone: list[SectionPlan],
) -> list[dict]:
    already_chosen = [
        {
            "section_id": s.section_id,
            "title": s.title,
            "block_kind": s.block_kind,
            "intent": s.intent,
        }
        for s in backbone
    ]
    user_payload = {
        "canonical_title": canonical_title,
        "entities": facts.entities,
        "what": facts.what,
        "when": facts.when,
        "where": facts.where,
        "why": facts.why,
        "already_chosen": already_chosen,
    }
    return [
        {
            "role": "system",
            "content": (
                BASE_PREAMBLE
                + "\n\n"
                + _BLOCK_KIND_CATALOG
                + "\n"
                + _INSTRUCTIONS
            ),
        },
        {
            "role": "user",
            "content": (
                "Curate 0–4 additional sections for the following event.\n\n"
                + json.dumps(user_payload, indent=2)
                + "\n\nOUTPUT a SectionPlanOutput now."
            ),
        },
    ]


__all__ = ["build_curation_messages"]
