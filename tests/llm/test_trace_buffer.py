from generator.llm.trace_buffer import push, drain, reset
from generator.schema import LLMCall

def _mk():
    return LLMCall(model="m", input_tokens=1, output_tokens=2, cost_usd=0.001, duration_ms=10)

def test_push_drain_returns_calls():
    reset()
    push(_mk()); push(_mk())
    out = drain()
    assert len(out) == 2
    assert drain() == []  # drained

def test_reset_clears():
    push(_mk())
    reset()
    assert drain() == []
