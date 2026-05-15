"""Hero image stage — best-effort Brave fetch."""

from __future__ import annotations

from generator.pipeline.hero_image import run_hero_image_stage
from generator.schema import HeroImage
from generator.sources.brave import BraveConfigError, BraveImageResult


async def test_returns_hero_when_brave_returns_results(monkeypatch):
    async def fake_brave(query, *, count=5, timeout=12.0):
        return [
            BraveImageResult(
                image_url="https://img.example/1.jpg",
                source_url="https://page.example/1",
                title="Kickoff at Estadio Azteca",
                publisher="Reuters",
            )
        ]
    monkeypatch.setattr(
        "generator.pipeline.hero_image.fetch_brave_images", fake_brave
    )
    out = await run_hero_image_stage("2026 FIFA World Cup")
    assert isinstance(out, HeroImage)
    assert str(out.image_url).startswith("https://img.example/")
    assert out.publisher == "Reuters"


async def test_returns_none_when_brave_unconfigured(monkeypatch):
    async def raising_brave(query, *, count=5, timeout=12.0):
        raise BraveConfigError("no key")
    monkeypatch.setattr(
        "generator.pipeline.hero_image.fetch_brave_images", raising_brave
    )
    out = await run_hero_image_stage("anything")
    assert out is None


async def test_returns_none_on_empty_results(monkeypatch):
    async def empty_brave(query, *, count=5, timeout=12.0):
        return []
    monkeypatch.setattr(
        "generator.pipeline.hero_image.fetch_brave_images", empty_brave
    )
    out = await run_hero_image_stage("anything")
    assert out is None


async def test_returns_none_on_unexpected_error(monkeypatch):
    async def crashing_brave(query, *, count=5, timeout=12.0):
        raise RuntimeError("network died")
    monkeypatch.setattr(
        "generator.pipeline.hero_image.fetch_brave_images", crashing_brave
    )
    out = await run_hero_image_stage("anything")
    assert out is None


async def test_returns_none_for_empty_canonical_title():
    out = await run_hero_image_stage("   ")
    assert out is None
