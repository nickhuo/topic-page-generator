"""Tavily Search HTTP API client (direct httpx, no tavily-python).

We POST to https://api.tavily.com/search with a JSON body. Response shape:
  {"results": [{"title", "url", "content", "published_date", "score"}, ...]}
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from generator.schema import Publisher, Source, SourceRights, SourceTier
from generator.sources._common import build_source_id, host_of
from generator.sources.publisher_tier import tier_for

_ENDPOINT = "https://api.tavily.com/search"
_TRANSIENT = (httpx.TimeoutException, httpx.NetworkError)


@retry(
    reraise=True,
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, max=4),
    retry=retry_if_exception_type(_TRANSIENT),
)
async def _post(client: httpx.AsyncClient, body: dict) -> httpx.Response:
    resp = await client.post(_ENDPOINT, json=body)
    if resp.status_code in (429, 500, 502, 503, 504):
        raise httpx.NetworkError(f"transient {resp.status_code}")
    return resp


def _publisher_name_from_host(host: str, tier: SourceTier) -> str:
    """Cheap, deterministic publisher name from host. Refined later (PR 4)."""
    if not host:
        return "Unknown"
    parts = host.split(".")
    base = parts[-2] if len(parts) >= 2 else parts[0]
    return base.capitalize()


async def fetch_tavily(
    query: str,
    time_range_days: int,
    max_results: int = 10,
    primary_entity: str | None = None,
) -> list[Source]:
    """Call Tavily Search and convert hits to Source records."""
    api_key = os.getenv("TAVILY_API_KEY")
    if not api_key:
        return []
    body = {
        "query": query,
        "max_results": max_results,
        "topic": "news",
        "days": time_range_days,
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    async with httpx.AsyncClient(timeout=15.0, headers=headers) as client:
        resp = await _post(client, body)
    if resp.status_code != 200:
        return []
    fetched_at = datetime.now(timezone.utc).isoformat()
    out: list[Source] = []
    for hit in resp.json().get("results", []):
        url = hit.get("url")
        if not url:
            continue
        host = host_of(url)
        tier = tier_for(url, primary_entity)
        published = hit.get("published_date")
        if published and "T" not in published:
            published = f"{published}T00:00:00Z"
        out.append(
            Source(
                id=build_source_id(url),
                url=url,
                publisher=Publisher(name=_publisher_name_from_host(host, tier), tier=tier),
                title=hit.get("title", url),
                author=None,
                published_at=published or fetched_at,
                fetched_at=fetched_at,
                language="en",  # Tavily doesn't return per-hit language; default 'en'
                rights=SourceRights(
                    max_excerpt_words=10000 if tier == "T0" else 30,
                    can_paraphrase=tier in ("T0", "T2"),
                ),
                archive_url=None,
            )
        )
    return out
