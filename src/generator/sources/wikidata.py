"""Wikidata SPARQL client. Two HTTP calls: search → SPARQL properties."""
from __future__ import annotations

from datetime import datetime, timezone

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from generator.schema import Publisher, Source, SourceRights
from generator.sources._common import build_source_id
from generator.sources.publisher_tier import tier_for

_SEARCH_URL = "https://www.wikidata.org/w/api.php"
_SPARQL_URL = "https://query.wikidata.org/sparql"
_USER_AGENT = "topic-page-generator/0.1 (https://example.com)"

_PROP_MAP = {
    "P31": "instance_of",
    "P585": "point_in_time",
    "P276": "location",
    "P17": "country",
    "P710": "participants",
}

_TRANSIENT = (httpx.TimeoutException, httpx.NetworkError)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(_TRANSIENT),
)
async def _get(client: httpx.AsyncClient, url: str, **kwargs) -> httpx.Response:
    resp = await client.get(url, **kwargs)
    if resp.status_code in (429, 500, 502, 503, 504):
        raise httpx.NetworkError(f"transient {resp.status_code}")
    return resp


def _sparql_for(qid: str) -> str:
    bindings = "\n".join(
        f"  OPTIONAL {{ wd:{qid} wdt:{pid} ?{label}. ?{label} rdfs:label ?{label}Label. FILTER(LANG(?{label}Label) = 'en') }}"
        for pid, label in _PROP_MAP.items()
    )
    select_labels = " ".join(f"?{label}Label" for label in _PROP_MAP.values())
    return f"SELECT {select_labels} WHERE {{\n{bindings}\n}} LIMIT 1"


async def fetch_wikidata(entity: str) -> tuple[Source | None, dict[str, str]]:
    """Resolve entity → Q-id → property dict + Source pointing at the Q-page."""
    headers = {"User-Agent": _USER_AGENT, "Accept": "application/sparql-results+json"}
    async with httpx.AsyncClient(headers=headers, timeout=10.0) as client:
        search = await _get(
            client,
            _SEARCH_URL,
            params={
                "action": "wbsearchentities",
                "search": entity,
                "language": "en",
                "format": "json",
                "limit": 1,
            },
        )
        if search.status_code != 200:
            return None, {}
        hits = search.json().get("search", [])
        if not hits:
            return None, {}
        qid = hits[0]["id"]

        sparql = await _get(
            client,
            _SPARQL_URL,
            params={"query": _sparql_for(qid), "format": "json"},
        )
        props: dict[str, str] = {}
        if sparql.status_code == 200:
            bindings = sparql.json().get("results", {}).get("bindings", [])
            if bindings:
                row = bindings[0]
                for label in _PROP_MAP.values():
                    cell = row.get(f"{label}Label")
                    if cell and "value" in cell:
                        props[label] = cell["value"]

    page_url = f"https://www.wikidata.org/wiki/{qid}"
    return (
        Source(
            id=build_source_id(page_url),
            url=page_url,
            publisher=Publisher(name="Wikidata", tier=tier_for(page_url)),
            title=hits[0].get("label", qid),
            author=None,
            published_at=datetime.now(timezone.utc).isoformat(),
            fetched_at=datetime.now(timezone.utc).isoformat(),
            language="en",
            rights=SourceRights(max_excerpt_words=10000, can_paraphrase=True),
            archive_url=None,
        ),
        props,
    )
