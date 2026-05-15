"""Ground stage prompt builder.

Replaces the old triage + disambiguate prompts. A single LLM call sees the
input sentence alongside fresh Tavily evidence and answers two questions
together: is this an unfolding hot event, and if so, what are the facts?
"""

from __future__ import annotations

from generator.prompts.base_preamble import BASE_PREAMBLE
from generator.schema import Source

_INSTRUCTIONS = """\
TASK: Ground a one-sentence event description in fresh evidence.

You will be given (1) a single sentence describing what the user wants a
topic page about, and (2) zero or more <evidence> blocks from a recent web
search. Decide whether this is an **unfolding hot event** worth a topic
page; if so, extract the basic facts. If not, explain why and stop.

Definition of "unfolding hot event":
- A real-world event that is happening now, imminent within ~30 days, or
  broke within the last ~7 days.
- Examples: product launches, breaking news, scheduled sports/cultural
  events, ongoing political situations, just-happened disasters.
- NOT a hot event: historical events (>30 days ago with no fresh
  development), evergreen reference questions ("how do Python decorators
  work"), opinions and recommendations, fictional or hypothetical
  scenarios, generic how-to queries.

Decision rule:
- If the <evidence> blocks contain zero items, OR all items are clearly
  evergreen/tutorial/reference content with no event-tied publication
  date, set `is_hot_event: false` and explain in `rejection_reason`.
- If at least one fresh news item describes the event, set
  `is_hot_event: true` and populate `facts` and `canonical_title`.

Field guidance when `is_hot_event=true`:
- `facts.entities` — All actors involved, in order of centrality. For
  multi-actor events (e.g. "Trump visits China") list every actor:
  ["Donald Trump", "China"]. For product launches, the first entry should
  be formatted as `<Subject Name> (<Organization>)` — e.g.
  "GPT-5.5 Instant (OpenAI)" — to enable downstream source-tier routing.
- `facts.what` — One factual sentence describing the event itself, in
  past or present tense depending on what the sources say.
- `facts.when` — ISO8601 datetime of the event. **MUST be sourced from a
  supporting evidence block's published date or in-body date — never
  guess from prior knowledge.** Omit if no source supports a specific
  date.
- `facts.where` — Location if any source explicitly states one. Omit
  otherwise.
- `facts.why` — One short clause of motivation/context, only if a source
  explicitly explains it. Optional.
- `facts.supporting_sources` — IDs of every evidence block that grounds
  one or more facts above. Must contain at least one ID.
- `canonical_title` — A clean, human-readable page title (≤80 chars)
  derived from `entities` and `what`. Avoid clickbait.
- `facts.subtitle` — A single descriptive sentence (≤240 chars) summarising
  the event. Must be grounded in the supporting evidence — paraphrase what
  the sources say. This becomes the page subtitle under the hero title.
  Avoid restating the title verbatim; add the so-what / stakes / context.

Field guidance when `is_hot_event=false`:
- `rejection_reason` — One sentence explaining what you saw. Examples:
  "No fresh news items in the last 14 days; query reads as evergreen."
  "All evidence describes a historical event from 1969 with no current
  development." Leave `facts` and `canonical_title` null.

`confidence` is your overall confidence in this judgment in [0, 1].
`reasoning` is one short sentence explaining the decision.
"""

_FEW_SHOT_HOT = """\
EXAMPLE — fresh multi-actor event:

INPUT: "Trump visits China this week"

<evidence id="src_a1b2">
Title: Trump arrives in Beijing for first state visit since re-election
Publisher: Reuters (T0)
URL: https://reuters.com/...
Published: 2026-05-14T08:30:00Z
</evidence>

<evidence id="src_c3d4">
Title: Xi and Trump expected to discuss trade tariffs in three-day summit
Publisher: AP (T0)
URL: https://apnews.com/...
Published: 2026-05-14T10:00:00Z
</evidence>

OUTPUT:
{
  "is_hot_event": true,
  "rejection_reason": null,
  "facts": {
    "entities": ["Donald Trump", "China"],
    "what": "Donald Trump arrived in Beijing for a state visit and summit with Xi Jinping.",
    "when": "2026-05-14T08:30:00Z",
    "where": "Beijing, China",
    "why": "First state visit since re-election; focus on trade tariffs.",
    "subtitle": "The first state visit of Trump's second term opens a three-day summit with Xi Jinping focused on trade tariffs.",
    "supporting_sources": ["src_a1b2", "src_c3d4"]
  },
  "canonical_title": "Trump's 2026 state visit to China",
  "confidence": 0.95,
  "reasoning": "Two T0 sources from today confirm an unfolding diplomatic event with named actors and date."
}
"""

_FEW_SHOT_NOT_HOT = """\
EXAMPLE — evergreen query:

INPUT: "Explain how Python decorators work"

(no <evidence> blocks, or only tutorial pages with no dates)

OUTPUT:
{
  "is_hot_event": false,
  "rejection_reason": "Query reads as an evergreen tutorial request; no time-bound event in the evidence.",
  "facts": null,
  "canonical_title": null,
  "confidence": 0.97,
  "reasoning": "How-to question about a stable language feature, not a news event."
}
"""


def build_ground_messages(sentence: str, evidence: list[Source]) -> list[dict]:
    blocks: list[str] = []
    for s in evidence[:8]:  # cap to keep prompt small
        blocks.append(
            f'<evidence id="{s.id}">\n'
            f"Title: {s.title}\n"
            f"Publisher: {s.publisher.name} ({s.publisher.tier})\n"
            f"URL: {s.url}\n"
            f"Published: {s.published_at}\n"
            f"</evidence>"
        )
    evidence_text = "\n\n".join(blocks) if blocks else "(no evidence retrieved)"
    user_payload = f"INPUT: {sentence!r}\n\n{evidence_text}\n\nOUTPUT:"
    return [
        {"role": "system", "content": BASE_PREAMBLE + "\n\n" + _INSTRUCTIONS},
        {"role": "system", "content": _FEW_SHOT_HOT},
        {"role": "system", "content": _FEW_SHOT_NOT_HOT},
        {"role": "user", "content": user_payload},
    ]
