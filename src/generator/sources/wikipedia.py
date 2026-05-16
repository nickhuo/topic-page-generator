"""Wikipedia REST summary fetcher for the reference sidebar card.

Calls the public `/api/rest_v1/page/summary/{title}` endpoint, which returns the
lead extract, thumbnail, and canonical article URL. Failures (network, 404,
empty body) collapse to None so callers can simply skip the card.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from generator.schema import WikipediaCardData

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0
_SUMMARY_MAX_CHARS = 600
_BASE_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/"
# Wikimedia API policy requires an identifying User-Agent. Without one the
# REST endpoint returns 403.
_USER_AGENT = (
    "topic-page-generator/0.1 (https://github.com/NickHuo/topic-page-generator) "
    "httpx/python"
)


def _truncate(text: str) -> str:
    if len(text) <= _SUMMARY_MAX_CHARS:
        return text
    # Reserve one character for the ellipsis to satisfy max_length=600.
    return text[: _SUMMARY_MAX_CHARS - 1] + "…"


async def fetch_wikipedia_card(title: str) -> WikipediaCardData | None:
    """Fetch the Wikipedia summary for `title`, or None on any failure."""
    url = _BASE_URL + quote(title, safe="")
    headers = {"Accept": "application/json", "User-Agent": _USER_AGENT}
    try:
        async with httpx.AsyncClient(
            timeout=_TIMEOUT_SECONDS, headers=headers
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            payload = resp.json()
    except httpx.HTTPError as exc:
        log.debug("Wikipedia fetch failed for %r: %s", title, exc)
        return None
    except ValueError as exc:  # JSON decode error
        log.debug("Wikipedia returned non-JSON for %r: %s", title, exc)
        return None

    extract = (payload.get("extract") or "").strip()
    content_urls = payload.get("content_urls") or {}
    article_url = (content_urls.get("desktop") or {}).get("page")
    if not extract or not article_url:
        return None

    thumbnail = (payload.get("thumbnail") or {}).get("source")
    page_title = payload.get("title") or title

    try:
        return WikipediaCardData(
            title=page_title,
            summary_text=_truncate(extract),
            thumbnail_url=thumbnail,
            article_url=article_url,
            retrieved_at=datetime.now(timezone.utc).isoformat(),
        )
    except ValueError as exc:
        log.debug("Wikipedia card validation rejected for %r: %s", title, exc)
        return None
