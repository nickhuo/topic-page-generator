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


def _pick_largest(results: list[BraveImageResult]) -> BraveImageResult:
    """Pick the largest-area result; preserve Brave's order as tie-breaker."""
    best_idx = 0
    best_score = (results[0].width or 0) * (results[0].height or 0)
    for i, r in enumerate(results[1:], start=1):
        score = (r.width or 0) * (r.height or 0)
        if score > best_score:
            best_idx = i
            best_score = score
    return results[best_idx]


async def run_hero_image_stage(
    canonical_title: str,
    *,
    count: int = 10,
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
    return _to_hero(_pick_largest(results))


__all__ = ["run_hero_image_stage"]
