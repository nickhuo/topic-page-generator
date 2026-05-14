"""Lightweight trace recorder used across pipeline stages."""
from __future__ import annotations

import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator

from generator.llm.trace_buffer import drain as _drain_llm_calls
from generator.schema import StageTrace, Trace, TraceApproval


class TraceRecorder:
    def __init__(self, input_sentence: str, page_id: str) -> None:
        self.trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        self.page_id = page_id
        self.input_sentence = input_sentence
        self.started_at = datetime.now(timezone.utc)
        self.stages: list[StageTrace] = []

    @contextmanager
    def stage(self, name: str, model: str | None = None) -> Iterator[None]:
        start = time.perf_counter()
        started_iso = datetime.now(timezone.utc).isoformat()
        try:
            yield
        except Exception as exc:  # surface error in trace and re-raise
            self.stages.append(
                StageTrace(
                    stage=name,
                    started_at=started_iso,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    model=model,
                    outcome="error",
                    error=str(exc),
                    llm_calls=_drain_llm_calls(),
                )
            )
            raise
        self.stages.append(
            StageTrace(
                stage=name,
                started_at=started_iso,
                duration_ms=int((time.perf_counter() - start) * 1000),
                model=model,
                outcome="success",
                llm_calls=_drain_llm_calls(),
            )
        )

    def finalize(self, auto_mode: bool = True) -> Trace:
        ended_at = datetime.now(timezone.utc)
        return Trace(
            trace_id=self.trace_id,
            page_id=self.page_id,
            input_sentence=self.input_sentence,
            started_at=self.started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            total_duration_ms=int((ended_at - self.started_at).total_seconds() * 1000),
            total_cost_usd=0.0,
            pipeline_trace=self.stages,
            editor_actions=[],
            final_outcome="auto_approved" if auto_mode else "approved_published",
            approval=TraceApproval(
                actor="cli_user@local",
                approved_at=ended_at.isoformat(),
                auto_mode=auto_mode,
            ),
        )
