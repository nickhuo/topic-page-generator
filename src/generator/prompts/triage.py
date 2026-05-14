"""Triage stage prompt builder."""
from __future__ import annotations

from generator.prompts.base_preamble import BASE_PREAMBLE

# Note: the (Organization) parenthetical is load-bearing — it lets
# generator/sources/publisher_tier.py:tier_for() route primary sources to T0.
_INSTRUCTIONS = """\
TASK: Classify a one-sentence event description.

You will be given a single sentence describing a news event. Produce a
TriageOutput JSON object capturing what the event is, what type it is, and
when it happened.

Field guidance:
- `primary_entity` — The thing the event is most centrally about. **If the
  subject is a product, release, version, campaign, or other artifact rather
  than the producing organization, format this as "<Subject Name>
  (<Organization>)" (e.g. "GPT-5.5 Instant (OpenAI)").** If the subject IS
  the organization or person, use the bare name. This format is required for
  downstream source-tier resolution.
- `event_type_hint` — One of: `product_launch`, `live_cultural_event`,
  `scheduled_sports_event`, `political_event`, `disaster`, `corporate_action`,
  `generic_event`. Pick the closest fit; never invent a new type.
- `temporal_posture` — `live` (happening now), `imminent` (within ~30 days),
  `recent` (within ~7 days), or `past` (>7 days).
- `time_anchor` — ISO8601 datetime of the event's reference moment. Use
  the most specific date implied by the sentence; otherwise omit.
- `confidence` — Your overall confidence in this classification, in [0, 1].
  Use < 0.85 only when the sentence is genuinely ambiguous (multiple
  defensible interpretations).
- `alternatives` — When confidence < 0.85, list 1–3 alternative
  interpretations with a one-line `rationale` each.
- `reasoning` — One or two short sentences explaining the classification.
"""

_FEW_SHOT_PRODUCT_LAUNCH = """\
EXAMPLE:

INPUT: "OpenAI rolled out GPT-5.5 Instant as the default model in ChatGPT in May 2026"

OUTPUT:
{
  "is_event": true,
  "primary_entity": "GPT-5.5 Instant (OpenAI)",
  "event_type_hint": "product_launch",
  "temporal_posture": "recent",
  "time_anchor": "2026-05-01T00:00:00Z",
  "confidence": 0.93,
  "alternatives": [],
  "reasoning": "Named product release by a known organization with explicit month and rollout verb."
}
"""


def build_triage_messages(sentence: str) -> list[dict]:
    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {"role": "system", "content": _FEW_SHOT_PRODUCT_LAUNCH},
        {"role": "user", "content": f"INPUT: {sentence!r}\n\nOUTPUT:"},
    ]
