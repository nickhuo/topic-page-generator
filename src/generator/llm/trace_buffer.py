"""Per-call LLM trace buffer.

Uses a contextvar so sequential stages don't bleed into each other. The buffer
is append-only: `push` mutates the list in place and never rebinds the var. This
matters for parallel stages — `asyncio.gather` copies the contextvar *binding*
into each child task, so the child shares the parent's list object and appends
are visible to the parent's `drain()`. If `push` rebound the var (`set`) inside a
child, that binding would be invisible to the parent and the calls would be lost.
The default is `None` (not a shared list) so a stray `push` before `reset` can't
pollute a module-level default across runs.
"""

from __future__ import annotations

from contextvars import ContextVar

from generator.schema import LLMCall

_buf: ContextVar[list[LLMCall] | None] = ContextVar("llm_calls", default=None)


def reset() -> None:
    _buf.set([])


def push(call: LLMCall) -> None:
    # Append-only: never rebind, so calls made inside asyncio.gather children
    # land in the same list the parent will drain.
    current = _buf.get()
    if current is None:
        current = []
        _buf.set(current)
    current.append(call)


def drain() -> list[LLMCall]:
    current = _buf.get()
    _buf.set([])
    return current or []
