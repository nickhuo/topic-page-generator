"""Aesthetic-plan stage prompt builder."""

from __future__ import annotations

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import EventFacts, NeedPlanOutput

_INSTRUCTIONS = """\
TASK: Pick an aesthetic preset for the event page.

Choose exactly one AestheticPresetId:
- `live_dominance` — for live, in-progress events (breaking news, ongoing
  ceremonies, championship night)
- `product_focus` — for product/tech launches (a model release, an iPhone
  drop)
- `imminent_event` — for scheduled future events in the run-up window
  (World Cup pre-kickoff, election eve)
- `reference` — fallback for generic entity pages / unclear tempo

You may also propose `aesthetic_overrides`:
- `palette`: festive_warm | minimal_tech | urgent_red | urgent_light |
  muted_solemn | bold_sport | neutral_news
- `density`: compact | standard | sparse
- `typography_weight`: tight | standard | loose
- `hero_mood`: solemn_portrait | celebratory_kinetic | minimalist_product |
  urgent_breaking | anticipatory_buildup | factual_neutral | data_focused |
  monumental_static
- `copy_register`: formal_official | warm_engaged | urgent_direct |
  somber_reflective | analytical_measured

If `preset_confidence < 0.75`, the system will fall back to `reference`.
Use that as a forcing function: only emit higher confidence when the choice
is unambiguous from the event's tempo and tone.
"""


def build_aesthetic_messages(
    facts: EventFacts,
    canonical_title: str,
    need_plan: NeedPlanOutput,
    evidence_preview: str,
) -> list[dict]:
    activated = [p for p in need_plan.need_plans if p.activated]
    activated_summary = ", ".join(
        f"{p.need_id}({p.rank})" for p in sorted(activated, key=lambda p: p.rank)
    )
    user_payload = (
        f"TITLE: {canonical_title}\n"
        f"ENTITIES: {', '.join(facts.entities)}\n"
        f"WHAT: {facts.what}\n"
        f"WHEN: {facts.when or 'unknown'}\n\n"
        f"PLAN: preset_hint={need_plan.layout_preset_id}, "
        f"activated_needs={activated_summary}\n\n"
        f"<evidence>\n{evidence_preview}\n</evidence>\n\nOUTPUT:"
    )
    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {"role": "user", "content": user_payload},
    ]
