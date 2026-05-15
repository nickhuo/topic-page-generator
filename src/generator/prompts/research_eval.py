"""Prompt builder for the research-eval (judge) LLM call.

Given a section + evidence digest, the LLM decides whether the pool covers
the acceptance criteria or whether one more refined search is needed.
"""

from __future__ import annotations

import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import SectionPlan, Source

_INSTRUCTIONS = """\
You are a research judge. Given a section and the current evidence pool,
decide whether the pool satisfies the section's acceptance criteria.

Output a JSON object:
  {"satisfied": true|false, "gaps": ["..."], "next_query_hint": "..." | null}

Rules:
1. Set satisfied=true only if the pool covers every facet listed in the
   section's acceptance criteria description, AND distinct-source / distinct-
   publisher counts meet min_sources / min_publishers.
2. If satisfied=false, "gaps" MUST list at least one specific concrete
   missing facet (e.g. "no source from before the announcement",
   "all sources from a single publisher").
3. "next_query_hint" is a one-line natural-language hint for the next
   Tavily query -- a person reading it should be able to type a query that
   probably fills the gap.
4. Do not output reasoning outside the JSON object.
"""


def build_research_eval_messages(
    *,
    section: SectionPlan,
    sources: list[Source],
    canonical_title: str,
) -> list[dict]:
    digest = [
        {
            "id": s.id,
            "publisher": s.publisher.name,
            "tier": s.publisher.tier,
            "title": s.title,
            "published_at": s.published_at,
            "summary": (s.summary or "")[:240],
        }
        for s in sources
    ]
    user_payload = {
        "canonical_title": canonical_title,
        "section": {
            "section_id": section.section_id,
            "title": section.title,
            "block_kind": section.block_kind,
            "intent": section.intent,
            "acceptance": {
                "description": section.acceptance.description,
                "min_sources": section.acceptance.min_sources,
                "min_publishers": section.acceptance.min_publishers,
                "required_facets": section.acceptance.required_facets,
                "forbid_single_perspective": section.acceptance.forbid_single_perspective,
            },
        },
        "evidence": digest,
    }
    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {
            "role": "user",
            "content": (
                "Evaluate whether this evidence pool satisfies the section.\n\n"
                + json.dumps(user_payload, indent=2)
                + "\n\nOUTPUT a ResearchEvalResult JSON now."
            ),
        },
    ]


__all__ = ["build_research_eval_messages"]
