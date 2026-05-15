"""Consistency-check stage: detect cross-module conflicts."""

from __future__ import annotations
import json

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import TypedModule

_INSTRUCTIONS = """\
Review the assembled modules for cross-module conflicts:
- date_mismatch: two modules cite different dates for the same event element
- contradictory_fact: numeric or attribute values disagree
- incoherent_combination: modules whose presence together makes no sense
   (e.g., schedule with no upcoming items for a "what's next" need, kpi_numbers without data)

For each issue, set:
  severity: "warning" | "error"
  module_kind: the kind to act on
  field_path: dotted path
  description: short explanation
  recommended_action: "regenerate" | "remove" | "manual_review"

If everything is internally consistent, return passes=true with issues=[].
"""


def build_consistency_messages(modules: list[TypedModule]) -> list[dict]:
    payload = [
        {"kind": m.kind, "data": m.data.model_dump(mode="json")} for m in modules
    ]
    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {"role": "user", "content": json.dumps(payload, indent=2)},
    ]
