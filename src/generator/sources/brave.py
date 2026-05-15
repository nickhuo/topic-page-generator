"""Brave Image Search API client.

Returns BraveImageResult objects suitable for downstream consumption by the
gallery block extractor. Designed to mirror the shape of tavily.py: async
httpx call, Pydantic response model, env-driven auth.
"""

from __future__ import annotations

import os
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, HttpUrl

BraveImageSize = Literal["small", "medium", "large", "wallpaper"]

_ENDPOINT = "https://api.search.brave.com/res/v1/images/search"
_MAX_COUNT = 200  # Brave's documented hard cap


class BraveConfigError(RuntimeError):
    """Raised when BRAVE_API_KEY is missing."""


class BraveImageResult(BaseModel):
    """One image hit from Brave Image Search."""

    model_config = ConfigDict(extra="forbid")

    image_url: HttpUrl  # the actual image to embed
    source_url: HttpUrl | None = None  # the page where the image was found
    title: str | None = None
    publisher: str | None = None
    width: int | None = None
    height: int | None = None
    thumbnail_url: HttpUrl | None = None


def _pick_image_url(item: dict[str, Any]) -> str | None:
    """Brave returns the image URL in one of several places; pick the best."""
    props = item.get("properties") or {}
    if isinstance(props, dict) and props.get("url"):
        return props["url"]
    img = item.get("image") or {}
    if isinstance(img, dict) and img.get("url"):
        return img["url"]
    thumb = item.get("thumbnail") or {}
    if isinstance(thumb, dict) and thumb.get("src"):
        return thumb["src"]
    return None


async def fetch_brave_images(
    query: str,
    *,
    count: int = 10,
    size: BraveImageSize | None = "large",
    timeout: float = 12.0,
) -> list[BraveImageResult]:
    """Fetch image results for `query`. Returns up to `count` items.

    `size` biases Brave toward a resolution bucket; pass None to omit the
    parameter entirely.

    Raises BraveConfigError if BRAVE_API_KEY is unset.
    Raises httpx.HTTPStatusError on non-2xx responses (caller decides recovery).
    """
    api_key = os.getenv("BRAVE_API_KEY")
    if not api_key:
        raise BraveConfigError("BRAVE_API_KEY not set")

    clamped = max(1, min(count, _MAX_COUNT))
    params: dict[str, Any] = {
        "q": query,
        "count": clamped,
        "safesearch": "strict",
        "spellcheck": "false",
        "country": "ALL",
    }
    if size is not None:
        params["size"] = size
    headers = {
        "X-Subscription-Token": api_key,
        "Accept": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(_ENDPOINT, params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()

    out: list[BraveImageResult] = []
    for item in payload.get("results", []):
        img_url = _pick_image_url(item)
        if not img_url:
            continue
        img_meta = item.get("image") or {}
        thumb = item.get("thumbnail") or {}
        try:
            out.append(
                BraveImageResult(
                    image_url=img_url,
                    source_url=item.get("url"),
                    title=item.get("title"),
                    publisher=item.get("source"),
                    width=img_meta.get("width") if isinstance(img_meta, dict) else None,
                    height=img_meta.get("height")
                    if isinstance(img_meta, dict)
                    else None,
                    thumbnail_url=thumb.get("src") if isinstance(thumb, dict) else None,
                )
            )
        except Exception:
            # Malformed item — skip rather than fail the whole fetch.
            continue
    return out


__all__ = ["BraveImageResult", "BraveConfigError", "fetch_brave_images"]
