"""Open Graph image enrichment.

Tavily's `images` array is a query-level pool, not per-article — most
news articles are served from one host but illustrated with CDN images
on a different host, so host-matching to attach thumbnails fails in
practice. This module fills the gap by fetching each article URL with a
short timeout and parsing `<meta property="og:image">` (and `twitter:image`
as a fallback) out of the HTML head.

Used by the block_extract stage for `newsfeed` sections, where every
rendered card must have a thumbnail.
"""

from __future__ import annotations

import asyncio
import logging
import re
from urllib.parse import urljoin

import httpx

from generator.schema import Source

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (compatible; topic-page-generator/0.1; +https://example.com/bot)"
)
# Only the head usually carries OG tags — cap the read to keep this cheap.
_MAX_BYTES = 96 * 1024
_DEFAULT_TIMEOUT = 4.0
_DEFAULT_CONCURRENCY = 8

# Match `<meta property="og:image" content="...">` (or twitter:image) in either
# attribute order. We do not parse full HTML — head <meta> tags are well-formed
# enough in practice that regex is faster and dependency-free.
_OG_PATTERNS = [
    re.compile(
        r"""<meta\s+[^>]*?property\s*=\s*["']og:image(?::secure_url)?["']"""
        r"""\s+[^>]*?content\s*=\s*["']([^"']+)["']""",
        re.IGNORECASE,
    ),
    re.compile(
        r"""<meta\s+[^>]*?content\s*=\s*["']([^"']+)["']"""
        r"""\s+[^>]*?property\s*=\s*["']og:image(?::secure_url)?["']""",
        re.IGNORECASE,
    ),
    re.compile(
        r"""<meta\s+[^>]*?name\s*=\s*["']twitter:image["']"""
        r"""\s+[^>]*?content\s*=\s*["']([^"']+)["']""",
        re.IGNORECASE,
    ),
]


def extract_og_image(html: str, base_url: str) -> str | None:
    """Return the first og:image / twitter:image URL found in `html`.

    Resolves relative URLs against `base_url`. Returns None when no match.
    """
    head = html[:_MAX_BYTES]
    for pattern in _OG_PATTERNS:
        m = pattern.search(head)
        if m:
            raw = m.group(1).strip()
            if not raw:
                continue
            return urljoin(base_url, raw)
    return None


async def _fetch_one(
    client: httpx.AsyncClient, source: Source, sem: asyncio.Semaphore
) -> None:
    if source.thumbnail_url is not None:
        return
    url = str(source.url)
    async with sem:
        try:
            resp = await client.get(url, follow_redirects=True)
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            logger.debug("og_image: fetch failed for %s: %s", url, exc)
            return
    if resp.status_code != 200:
        logger.debug("og_image: %s -> %s", url, resp.status_code)
        return
    # Pydantic HttpUrl validation will raise on garbage — guard with try.
    image_url = extract_og_image(resp.text, base_url=str(resp.url))
    if not image_url:
        return
    try:
        source.thumbnail_url = image_url  # type: ignore[assignment]
    except Exception as exc:
        logger.debug("og_image: invalid url for %s: %s (%s)", url, image_url, exc)


async def _fetch_og_image(client: httpx.AsyncClient, url: str) -> str | None:
    """Single-URL helper: fetch page, parse og:image. Returns None on any failure."""
    try:
        resp = await client.get(url, follow_redirects=True)
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        logger.debug("og_image: fetch failed for %s: %s", url, exc)
        return None
    if resp.status_code != 200:
        logger.debug("og_image: %s -> %s", url, resp.status_code)
        return None
    return extract_og_image(resp.text, base_url=str(resp.url))


async def enrich_news_card_thumbnails(
    cards: list,
    *,
    concurrency: int = _DEFAULT_CONCURRENCY,
    timeout: float = _DEFAULT_TIMEOUT,
) -> list:
    """Return a new list of NewsCards with thumbnail_url populated where possible.

    NewsCard is frozen — cards that get a hit are replaced via model_copy;
    others pass through unchanged. Cards already carrying a thumbnail_url are
    untouched.
    """
    if not cards:
        return cards
    targets: list[tuple[int, str]] = [
        (i, str(c.url)) for i, c in enumerate(cards) if c.thumbnail_url is None
    ]
    if not targets:
        return cards
    sem = asyncio.Semaphore(max(1, concurrency))
    limits = httpx.Limits(max_connections=concurrency * 2)

    async def _bound(url: str) -> str | None:
        async with sem:
            return await _fetch_og_image(client, url)

    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        limits=limits,
    ) as client:
        results = await asyncio.gather(
            *(_bound(url) for _, url in targets),
            return_exceptions=True,
        )

    out = list(cards)
    for (idx, _url), image_url in zip(targets, results, strict=True):
        if isinstance(image_url, Exception) or not image_url:
            continue
        try:
            out[idx] = cards[idx].model_copy(update={"thumbnail_url": image_url})
        except Exception as exc:  # invalid URL → leave unchanged
            logger.debug("og_image: invalid url %s (%s)", image_url, exc)
    return out


async def enrich_thumbnails(
    sources: list[Source],
    *,
    concurrency: int = _DEFAULT_CONCURRENCY,
    timeout: float = _DEFAULT_TIMEOUT,
) -> None:
    """Populate `thumbnail_url` on each source by parsing its og:image tag.

    Mutates sources in place. No-ops for sources that already have a thumbnail
    or whose fetch fails — image-less sources stay image-less, and the
    downstream postprocess will drop them from the newsfeed.
    """
    targets = [s for s in sources if s.thumbnail_url is None]
    if not targets:
        return
    sem = asyncio.Semaphore(max(1, concurrency))
    limits = httpx.Limits(max_connections=concurrency * 2)
    async with httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": _USER_AGENT, "Accept": "text/html,*/*;q=0.8"},
        limits=limits,
    ) as client:
        await asyncio.gather(
            *(_fetch_one(client, s, sem) for s in targets),
            return_exceptions=True,
        )


__all__ = ["enrich_news_card_thumbnails", "enrich_thumbnails", "extract_og_image"]
