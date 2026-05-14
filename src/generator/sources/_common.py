"""Shared helpers for the source clients."""

from __future__ import annotations

import hashlib
from urllib.parse import urlparse


def build_source_id(url: str) -> str:
    """Stable, deterministic id derived from URL — same URL → same id across runs."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"src_{digest}"


def host_of(url: str) -> str:
    """Extract lowercased hostname, stripping a leading `www.`."""
    host = (urlparse(url).hostname or "").lower()
    return host[4:] if host.startswith("www.") else host
