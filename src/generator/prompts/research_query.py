"""Prompt builder for the research-query LLM call.

Used inside the per-section research loop. On iteration 1, produces an
initial Tavily query from the section's intent and acceptance criteria. On
iteration >=2, refines based on `previous_gaps` and the `previous_query`
that didn't work.
"""

from __future__ import annotations

import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import EventFacts, SectionPlan

_INSTRUCTIONS = """\
You generate a single Tavily search query for one section of an event page.

Output a JSON object with one field:
  {"query": "..."}

Rules:
1. Query length: 4-12 words.
2. Anchor on the event's canonical title and the section's information need.
3. If the section's block_kind is "timeline", bias toward date-oriented terms
   ("when", "schedule", "announced", year/month).
4. If the section's block_kind is "newsfeed", bias toward publication terms
   ("coverage", "reactions", "analysis").
5. If the section's block_kind is "factsheet", bias toward reference terms
   ("specs", "details", "lineup", "list").
6. If previous_gaps and previous_query are supplied, your new query MUST
   differ meaningfully from previous_query and target one of the gaps.
"""


def build_research_query_messages(
    *,
    facts: EventFacts,
    canonical_title: str,
    section: SectionPlan,
    previous_gaps: list[str] | None,
    previous_query: str | None,
) -> list[dict]:
    user_payload = {
        "canonical_title": canonical_title,
        "entities": facts.entities,
        "what": facts.what,
        "when": facts.when,
        "where": facts.where,
        "section": {
            "section_id": section.section_id,
            "title": section.title,
            "block_kind": section.block_kind,
            "intent": section.intent,
            "acceptance": section.acceptance.description,
        },
    }
    if previous_gaps:
        user_payload["previous_gaps"] = previous_gaps
        user_payload["previous_query"] = previous_query

    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                "Generate one Tavily query for the following section.\n\n"
                + json.dumps(user_payload, indent=2)
                + '\n\nOUTPUT a JSON object {"query": "..."} now.'
            ),
        },
    ]


__all__ = ["build_research_query_messages"]
