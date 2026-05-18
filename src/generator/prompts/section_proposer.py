"""Prompt builder for the editor-triggered section proposer.

When the editor types a natural-language description at the plan_review HITL
gate, this builder asks the LLM to convert it into a single valid
SectionPlan (kind="curated"). Backbone slots are forbidden — the LLM only
fills in extra sections.
"""

from __future__ import annotations

import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.prompts.curation import BLOCK_KIND_CATALOG
from generator.schema import EventFacts

_INSTRUCTIONS = """\
You are the section proposer. The editor has typed a natural-language
description of a new section they want added to the page. Your job: convert
their description into ONE valid SectionPlan.

Rules:
1. Output exactly one section (the editor proposed one).
2. `kind` must be `"curated"`. Never propose a backbone kind.
3. `section_id` is a fresh snake_case slug (e.g. "sponsor_reactions"). It
   MUST NOT collide with any id in `existing_section_ids`.
4. `block_kind` must be one of the closed-enum kinds listed in the catalog.
5. `title`: short human-readable section title (≤ 60 chars).
6. `intent`: one sentence describing what the section answers and how.
7. `acceptance.description`: one sentence describing what success looks like.
   Set `min_sources` and `min_publishers` honestly.
8. Honor the editor's description as a hard constraint — pick the block_kind
   that best fits their intent. If the description is too vague to map to a
   block_kind, default to `paragraph`.

Strict output: a single JSON object with fields section_id, title,
block_kind, intent, acceptance{description,min_sources,min_publishers}.
"""


def build_section_proposer_messages(
    *,
    description: str,
    facts: EventFacts,
    canonical_title: str,
    existing_section_ids: list[str],
) -> list[dict]:
    user_payload = {
        "canonical_title": canonical_title,
        "entities": facts.entities,
        "what": facts.what,
        "when": facts.when,
        "where": facts.where,
        "existing_section_ids": existing_section_ids,
        "editor_description": description,
    }
    return [
        {
            "role": "system",
            "content": (
                BASE_PREAMBLE + "\n\n" + BLOCK_KIND_CATALOG + "\n" + _INSTRUCTIONS
            ),
        },
        {
            "role": "user",
            "content": (
                "Convert the editor's description below into one SectionPlan.\n\n"
                + json.dumps(user_payload, indent=2)
                + "\n\nOUTPUT a single section JSON now."
            ),
        },
    ]


__all__ = ["build_section_proposer_messages"]
