"""People block spec — profile cards for "Who is involved" needs."""

from __future__ import annotations

from typing import ClassVar

from generator.blocks.schema import PeopleBlockData
from generator.blocks.specs.base import BlockSpec
from generator.schema import AcceptanceCriteria

PEOPLE_MIN_CARDS = 2
PEOPLE_MAX_CARDS = 6


class PeopleBlockSpec(BlockSpec):
    kind: ClassVar = "people"
    data_schema: ClassVar = PeopleBlockData
    template_path: ClassVar = "blocks/people.html"
    default_acceptance: ClassVar = AcceptanceCriteria(
        description=(
            "2-6 people materially involved in the event, each with role and a "
            "one-to-two sentence bio. Portraits prefer Wikipedia/Wikidata; "
            "Brave search is a fallback when neither is available."
        ),
        min_sources=2,
        min_publishers=2,
        required_facets=["name", "role"],
    )

    extraction_prompt_fragment: ClassVar = """\
Output a `people` block.

Schema:
- cards: 2-6 PersonCard. Each has:
    - name (full name as written in sources)
    - role (one line: title + affiliation, e.g. "FIFA President")
    - bio (1-2 neutral sentences, <=260 chars, answering "why are they
      relevant to THIS event?" — not a general biography)
    - image_url (optional)
    - image_source: "wikipedia" | "wikidata" | "brave" | "none"
    - image_credit_url (optional — link back to where the image came from)
    - profile_url (optional — Wikipedia / official page)
    - source_ids (>=1 supporting source from the evidence pool)

HARD RULES:
- Include only people MATERIALLY involved (decision-makers, official
  spokespeople, victims, headline performers, key analysts). Skip casual
  mentions, generic crowds, or third-party commentators.
- Names must appear VERBATIM in the cited sources.
- Use the supplied PEOPLE_IMAGE_MANIFEST for image_url/image_source — do NOT
  invent image URLs. If no manifest entry exists, set image_source="none".
- `bio` must be event-specific, not a Wikipedia summary.
"""

    def is_minimum_viable(self, data: PeopleBlockData) -> bool:
        usable = [c for c in data.cards if c.name and c.role and c.bio]
        return len(usable) >= PEOPLE_MIN_CARDS
