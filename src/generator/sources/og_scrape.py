"""OpenGraph scraping to enrich sources with thumbnails and summaries.

When Tavily doesn't return an image for a hit, we fetch the URL's HTML head and
parse `<meta property="og:image">` / `og:description` ourselves. Bounded
concurrency, short timeout, graceful failure (missing fields stay None).

Selectolax is a small, fast HTML5 parser (cython-backed lexbor). We only need
to read <meta> tags from the document head, so its narrow API is enough.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from pydantic import HttpUrl, TypeAdapter

from generator.schema import Source

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)

log = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 5.0
_CONCURRENCY = 8
_MAX_HTML_BYTES = 256_000  # 256 KB head is plenty for <meta> tags
_USER_AGENT = (
    "Mozilla/5.0 (compatible; topic-page-generator/0.1; +https://example.invalid)"
)


def _parse_og_from_html(html: str) -> dict[str, str]:
    """Extract og:image and og:description (or twitter: fallback) from HTML."""
    try:
        from selectolax.parser import HTMLParser
    except ImportError:  # pragma: no cover - dev env should always have it
        log.warning("selectolax not installed; OG scrape disabled.")
        return {}
    tree = HTMLParser(html)
    out: dict[str, str] = {}
    for meta in tree.css("meta"):
        prop = meta.attributes.get("property") or meta.attributes.get("name") or ""
        content = meta.attributes.get("content") or ""
        if not content:
            continue
        if prop in ("og:image", "twitter:image") and "image" not in out:
            out["image"] = content
        elif (
            prop in ("og:description", "twitter:description", "description")
            and "description" not in out
        ):
            out["description"] = content
        if "image" in out and "description" in out:
            break
    return out


async def _enrich_one(client: httpx.AsyncClient, source: Source) -> Source:
    needs_image = source.thumbnail_url is None
    needs_summary = source.summary is None
    if not needs_image and not needs_summary:
        return source
    try:
        async with client.stream("GET", str(source.url), follow_redirects=True) as resp:
            if resp.status_code >= 400:
                return source
            content_type = resp.headers.get("content-type", "")
            if "html" not in content_type.lower():
                return source
            chunks: list[bytes] = []
            total = 0
            async for chunk in resp.aiter_bytes():
                chunks.append(chunk)
                total += len(chunk)
                if total >= _MAX_HTML_BYTES:
                    break
            html = b"".join(chunks).decode("utf-8", errors="replace")
    except (httpx.HTTPError, UnicodeDecodeError) as exc:
        log.debug("OG fetch failed for %s: %s", source.url, exc)
        return source

    og = _parse_og_from_html(html)
    update: dict = {}
    if needs_image and "image" in og:
        # Validate URL shape — pydantic HttpUrl rejects invalid ones.
        try:
            update["thumbnail_url"] = _HTTP_URL_ADAPTER.validate_python(og["image"])
        except ValueError:
            pass
    if needs_summary and "description" in og:
        update["summary"] = og["description"][:280]
    if update:
        update["enriched_at"] = datetime.now(timezone.utc).isoformat()
        try:
            return source.model_copy(update=update)
        except ValueError as exc:
            log.debug("OG enrich validation rejected: %s", exc)
            return source
    return source


async def enrich_sources(sources: list[Source]) -> list[Source]:
    """Concurrently enrich each source's missing thumbnail / summary."""
    if not sources:
        return sources
    sem = asyncio.Semaphore(_CONCURRENCY)
    headers = {"User-Agent": _USER_AGENT, "Accept": "text/html,*/*"}

    async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, headers=headers) as client:

        async def _bounded(s: Source) -> Source:
            async with sem:
                return await _enrich_one(client, s)

        return await asyncio.gather(*(_bounded(s) for s in sources))
