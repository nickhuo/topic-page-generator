"""Per-call LLM trace buffer. Uses contextvars so async stages don't bleed."""
from __future__ import annotations

from contextvars import ContextVar

from generator.schema import LLMCall

_buf: ContextVar[list[LLMCall]] = ContextVar("llm_calls", default=[])


def reset() -> None:
    _buf.set([])


def push(call: LLMCall) -> None:
    # ContextVar values are shared by reference within a context;
    # mutate-then-set keeps the same list visible to readers inside the same task.
    current = _buf.get()
    if current is _buf.get(None) and isinstance(current, list):
        current.append(call)
    else:
        _buf.set([call])


def drain() -> list[LLMCall]:
    current = _buf.get()
    _buf.set([])
    return current
