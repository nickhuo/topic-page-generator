import asyncio

from generator.llm.trace_buffer import push, drain, reset
from generator.schema import LLMCall


def _mk():
    return LLMCall(
        model="m", input_tokens=1, output_tokens=2, cost_usd=0.001, duration_ms=10
    )


def test_push_drain_returns_calls():
    reset()
    push(_mk())
    push(_mk())
    out = drain()
    assert len(out) == 2
    assert drain() == []  # drained


def test_reset_clears():
    push(_mk())
    reset()
    assert drain() == []


async def test_push_inside_gather_is_captured_by_parent():
    """Regression: calls pushed inside asyncio.gather children must reach the
    parent's drain(). A contextvar rebind in push() would lose them (the bug
    that left research/block_extract stages with empty llm_calls)."""

    async def _child() -> None:
        push(_mk())

    reset()
    await asyncio.gather(*[_child() for _ in range(5)])
    out = drain()
    assert len(out) == 5

