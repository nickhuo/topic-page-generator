"""Hero image fetch — always-on decorative image for the page chrome.

Single Brave Image Search call. Returns the first usable result wrapped in a
HeroImage. Returns None on any failure (missing key, network error, empty
results) — the page chrome handles None gracefully.
"""

from __future__ import annotations

import logging

from generator.schema import HeroImage
from generator.sources.brave import (
    BraveConfigError,
    BraveImageResult,
    fetch_brave_images,
)

logger = logging.getLogger(__name__)


def _to_hero(result: BraveImageResult) -> HeroImage:
    return HeroImage(
        image_url=result.image_url,
        alt_text=result.title,
        source_url=result.source_url,
        publisher=result.publisher,
    )


async def run_hero_image_stage(
    canonical_title: str,
    *,
    count: int = 5,
) -> HeroImage | None:
    """Best-effort hero image fetch. Never raises."""
    if not canonical_title.strip():
        return None
    try:
        results = await fetch_brave_images(canonical_title, count=count)
    except BraveConfigError:
        logger.info("BRAVE_API_KEY not set — hero image skipped")
        return None
    except Exception as exc:
        logger.warning("hero image fetch failed: %s", exc)
        return None
    if not results:
        return None
    return _to_hero(results[0])


__all__ = ["run_hero_image_stage"]
