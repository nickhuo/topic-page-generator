"""Stage 4 — Fetch. Stub returns one mock Source."""
from __future__ import annotations

from generator.schema import Publisher, Source, SourceRights


def run() -> list[Source]:
    return [
        Source(
            id="src_001",
            url="https://openai.com/blog/gpt-5-5-instant",
            publisher=Publisher(name="OpenAI", tier="T0"),
            title="Introducing GPT-5.5 Instant",
            author="OpenAI",
            published_at="2026-05-01T15:00:00Z",
            fetched_at="2026-05-13T12:00:00Z",
            language="en",
            rights=SourceRights(max_excerpt_words=10000, can_paraphrase=True),
        ),
        Source(
            id="src_002",
            url="https://www.reuters.com/technology/openai-gpt-55-instant",
            publisher=Publisher(name="Reuters", tier="T1"),
            title="OpenAI rolls out GPT-5.5 Instant as ChatGPT default",
            author="Jane Doe",
            published_at="2026-05-02T09:00:00Z",
            fetched_at="2026-05-13T12:00:00Z",
            language="en",
            rights=SourceRights(max_excerpt_words=30, can_paraphrase=False),
        ),
    ]
