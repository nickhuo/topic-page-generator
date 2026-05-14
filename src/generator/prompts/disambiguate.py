"""Disambiguate stage prompt builder."""
from __future__ import annotations

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import Source, TriageOutput

_INSTRUCTIONS = """\
TASK: Resolve an ambiguous event interpretation against retrieved evidence.

You will receive (1) a TriageOutput object with low confidence and a list of
candidate interpretations, and (2) one or more <evidence> blocks with web
search results. Pick the interpretation best supported by the evidence.

Output a DisambiguationOutput JSON object:
- If exactly one candidate is clearly supported, set `resolved: true` and
  populate `chosen` (entity, event_type_hint, time_anchor, supporting_sources).
- If two or more candidates remain plausible after reading the evidence, set
  `resolved: false` and populate `unresolved_candidates` (≤3 items, each with
  rationale and supporting_sources).
- Always include at least one `source_id` in `supporting_sources`.
"""

_FEW_SHOT_AMBIGUOUS = """\
EXAMPLE — ambiguous input "Apollo program launched today":

TRIAGE:
{"is_event": true, "primary_entity": "Apollo program", "confidence": 0.4,
 "alternatives": [
   {"entity": "Apollo program (NASA crewed lunar program)", "event_type_hint": "anniversary_event", "rationale": "Historical reference."},
   {"entity": "Apollo (SpaceX merch line)", "event_type_hint": "product_launch", "rationale": "Recent retail launch."}
 ]}

<evidence id="src_abc123">
Title: SpaceX launches Apollo merch line on its store today (2026-05-13)
Snippet: SpaceX began selling the Apollo lifestyle line on its online store...
</evidence>

OUTPUT:
{
  "resolved": true,
  "chosen": {
    "entity": "Apollo (SpaceX merch line)",
    "event_type_hint": "product_launch",
    "time_anchor": "2026-05-13T00:00:00Z",
    "supporting_sources": ["src_abc123"]
  },
  "unresolved_candidates": []
}
"""


def build_disambiguate_messages(triage: TriageOutput, evidence: list[Source]) -> list[dict]:
    triage_json = triage.model_dump_json(indent=2, exclude_none=True)
    blocks: list[str] = []
    for s in evidence[:8]:  # cap to keep prompt small
        blocks.append(
            f'<evidence id="{s.id}">\n'
            f'Title: {s.title}\n'
            f'Publisher: {s.publisher.name} ({s.publisher.tier})\n'
            f'URL: {s.url}\n'
            f'Published: {s.published_at}\n'
            f'</evidence>'
        )
    user_payload = "TRIAGE:\n" + triage_json + "\n\n" + "\n\n".join(blocks) + "\n\nOUTPUT:"
    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {"role": "system", "content": _FEW_SHOT_AMBIGUOUS},
        {"role": "user", "content": user_payload},
    ]
