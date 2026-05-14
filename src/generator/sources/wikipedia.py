"""Wikipedia REST API client. Returns at most one Source per entity."""
from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import quote

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

_REST_BASE = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
_SEARCH_URL = "https://{lang}.wikipedia.org/w/api.php"
_USER_AGENT = "topic-page-generator/0.1 (https://example.com)"

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


async def _resolve_title(client: httpx.AsyncClient, entity: str, lang: str) -> str | None:
    """Try direct lookup; fall back to search."""
    direct = await _get(
        client, _REST_BASE.format(lang=lang, title=quote(entity, safe=""))
    )
    if direct.status_code == 200:
        return entity
    search = await _get(
        client,
        _SEARCH_URL.format(lang=lang),
        params={
            "action": "query",
            "list": "search",
            "srsearch": entity,
            "format": "json",
            "srlimit": 1,
        },
    )
    if search.status_code != 200:
        return None
    hits = search.json().get("query", {}).get("search", [])
    return hits[0]["title"] if hits else None


async def fetch_wikipedia(entity: str, lang: str = "en") -> Source | None:
    """Resolve `entity` → Wikipedia article → Source, or None if no article exists."""
    async with httpx.AsyncClient(
        headers={"User-Agent": _USER_AGENT}, timeout=10.0
    ) as client:
        title = await _resolve_title(client, entity, lang)
        if title is None:
            return None
        resp = await _get(
            client, _REST_BASE.format(lang=lang, title=quote(title, safe=""))
        )
        if resp.status_code != 200:
            return None
        data = resp.json()

    page_url = data.get("content_urls", {}).get("desktop", {}).get("page")
    if not page_url:
        return None
    published_at = data.get("timestamp") or datetime.now(timezone.utc).isoformat()
    fetched_at = datetime.now(timezone.utc).isoformat()
    return Source(
        id=build_source_id(page_url),
        url=page_url,
        publisher=Publisher(name="Wikipedia", tier=tier_for(page_url)),
        title=data.get("title") or title,
        author=None,
        published_at=published_at,
        fetched_at=fetched_at,
        language=data.get("lang", lang),
        rights=SourceRights(max_excerpt_words=10000, can_paraphrase=True),
        archive_url=None,
    )
