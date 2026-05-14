"""Static publisher-tier map and resolver. No I/O, no side effects."""

from __future__ import annotations

from generator.schema import SourceTier
from generator.sources._common import host_of

# T1: independent tier-1 international news outlets.
# T2: open reference data sources.
# Everything not listed falls through to T3.
PUBLISHER_TIERS: dict[str, SourceTier] = {
    # T1 — wires
    "reuters.com": "T1",
    "apnews.com": "T1",
    "afp.com": "T1",
    # T1 — international broadcasters / dailies
    "bbc.com": "T1",
    "bbc.co.uk": "T1",
    "nytimes.com": "T1",
    "wsj.com": "T1",
    "washingtonpost.com": "T1",
    "ft.com": "T1",
    "theguardian.com": "T1",
    "economist.com": "T1",
    # T1 — financial / tech business press
    "bloomberg.com": "T1",
    "cnbc.com": "T1",
    "axios.com": "T1",
    # T1 — broadcast (US)
    "cnn.com": "T1",
    "nbcnews.com": "T1",
    "cbsnews.com": "T1",
    "abcnews.go.com": "T1",
    # T1 — tech-focused tier-1
    "theverge.com": "T1",
    "wired.com": "T1",
    "arstechnica.com": "T1",
    "techcrunch.com": "T1",
    # T2 — reference
    "en.wikipedia.org": "T2",
    "wikipedia.org": "T2",
    "wikidata.org": "T2",
}

# T0 is contextual: a domain is T0 only for events about that entity.
# Match keys via case-insensitive substring against the resolved primary_entity.
T0_DOMAINS_BY_ENTITY: dict[str, set[str]] = {
    "openai": {"openai.com"},
    "anthropic": {"anthropic.com"},
    "google": {"deepmind.com", "ai.google.dev", "blog.google"},
    "fifa": {"fifa.com"},
    "eurovision": {"eurovision.tv", "eurovision.com"},
    "uefa": {"uefa.com"},
    "olympic": {"olympics.com"},
    "white house": {"whitehouse.gov"},
    "nasa": {"nasa.gov"},
}


def tier_for(url: str, primary_entity: str | None = None) -> SourceTier:
    """Resolve a URL to its SourceTier.

    Order:
      1. T0 — only if `primary_entity` is provided AND its (case-insensitive)
         text contains one of the T0_DOMAINS_BY_ENTITY keys AND the URL's host
         is in that key's domain set.
      2. T1/T2 — direct lookup in PUBLISHER_TIERS by host.
      3. T3 — fallback.
    """
    host = host_of(url)
    if primary_entity:
        entity_lower = primary_entity.lower()
        for entity_key, domains in T0_DOMAINS_BY_ENTITY.items():
            if entity_key in entity_lower and host in domains:
                return "T0"
    return PUBLISHER_TIERS.get(host, "T3")
