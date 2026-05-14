"""Per-call LLM trace buffer. Uses contextvars so async stages don't bleed."""
from __future__ import annotations

from contextvars import ContextVar

from generator.schema import LLMCall

_buf: ContextVar[list[LLMCall]] = ContextVar("llm_calls", default=[])


def reset() -> None:
    _buf.set([])


def push(call: LLMCall) -> None:
    # Only mutate non-empty lists; otherwise set a fresh one to avoid shared default.
    current = _buf.get()
    if not current:
        _buf.set([call])
    else:
        current.append(call)


def drain() -> list[LLMCall]:
    current = _buf.get()
    _buf.set([])
    return current
