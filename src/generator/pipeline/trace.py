"""Lightweight trace recorder used across pipeline stages."""

from __future__ import annotations

import os
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from generator.llm.trace_buffer import drain as _drain_llm_calls
from generator.schema import (
    EditorAction,
    LLMCall,
    StageTokens,
    StageTrace,
    Trace,
    TraceApproval,
)


def _rollup(calls: list[LLMCall]) -> tuple[float | None, StageTokens | None, str | None]:
    """Aggregate per-call cost/tokens/model into stage-level fields."""
    if not calls:
        return None, None, None
    cost = round(sum(c.cost_usd for c in calls), 6)
    tokens = StageTokens(
        input=sum(c.input_tokens for c in calls),
        output=sum(c.output_tokens for c in calls),
    )
    # Stages may route to one model; report it when unambiguous.
    models = {c.model for c in calls}
    model = next(iter(models)) if len(models) == 1 else None
    return cost, tokens, model


class TraceRecorder:
    def __init__(self, input_sentence: str, page_id: str) -> None:
        self.trace_id = f"trace_{uuid.uuid4().hex[:12]}"
        self.page_id = page_id
        self.input_sentence = input_sentence
        self.started_at = datetime.now(timezone.utc)
        self.stages: list[StageTrace] = []
        self._editor_actions: list[EditorAction] = []

    @contextmanager
    def stage(self, name: str, model: str | None = None) -> Iterator[None]:
        start = time.perf_counter()
        started_iso = datetime.now(timezone.utc).isoformat()
        try:
            yield
        except Exception as exc:  # surface error in trace and re-raise
            calls = _drain_llm_calls()
            cost, tokens, rolled_model = _rollup(calls)
            self.stages.append(
                StageTrace(
                    stage=name,
                    started_at=started_iso,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                    model=model or rolled_model,
                    tokens=tokens,
                    cost_usd=cost,
                    outcome="error",
                    error=str(exc),
                    llm_calls=calls,
                )
            )
            raise
        calls = _drain_llm_calls()
        cost, tokens, rolled_model = _rollup(calls)
        self.stages.append(
            StageTrace(
                stage=name,
                started_at=started_iso,
                duration_ms=int((time.perf_counter() - start) * 1000),
                model=model or rolled_model,
                tokens=tokens,
                cost_usd=cost,
                outcome="success",
                llm_calls=calls,
            )
        )

    def record_editor_action(self, action: EditorAction) -> None:
        self._editor_actions.append(action)

    def _total_cost(self) -> float:
        return round(sum(s.cost_usd or 0.0 for s in self.stages), 6)

    def _snapshot(self, *, final_outcome: str = "in_progress") -> Trace:
        """Build a Trace from current state without ending the run."""
        now = datetime.now(timezone.utc)
        return Trace(
            trace_id=self.trace_id,
            page_id=self.page_id,
            input_sentence=self.input_sentence,
            started_at=self.started_at.isoformat(),
            ended_at=now.isoformat(),
            total_duration_ms=int((now - self.started_at).total_seconds() * 1000),
            total_cost_usd=self._total_cost(),
            pipeline_trace=list(self.stages),
            editor_actions=list(self._editor_actions),
            final_outcome=final_outcome,  # type: ignore[arg-type]
            approval=TraceApproval(
                actor="cli_user@local",
                approved_at=None,
                auto_mode=False,
            ),
        )

    def flush_partial(self, out_dir: Path, basename: str) -> Path:
        """Atomically write the current trace snapshot to {out_dir}/{basename}.trace.json.

        Schema validation of `final_outcome` only allows the four published
        values, so on partial flush we use "draft_saved" as a stand-in.
        """
        out_dir.mkdir(parents=True, exist_ok=True)
        target = out_dir / f"{basename}.trace.json"
        # "draft_saved" is the closest published-enum value to "in progress".
        snapshot = self._snapshot(final_outcome="draft_saved")
        payload = snapshot.model_dump_json(indent=2)
        fd, tmp_path = tempfile.mkstemp(
            prefix=f".{basename}.trace.", suffix=".tmp", dir=str(out_dir)
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            os.replace(tmp_path, target)
        except Exception:
            # Clean up tmp on failure; never raise from a flush.
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
        return target

    def finalize(
        self, *, auto_mode: bool = True, final_outcome: str | None = None
    ) -> Trace:
        ended_at = datetime.now(timezone.utc)
        if final_outcome is None:
            final_outcome = "auto_approved" if auto_mode else "approved_published"
        return Trace(
            trace_id=self.trace_id,
            page_id=self.page_id,
            input_sentence=self.input_sentence,
            started_at=self.started_at.isoformat(),
            ended_at=ended_at.isoformat(),
            total_duration_ms=int((ended_at - self.started_at).total_seconds() * 1000),
            total_cost_usd=self._total_cost(),
            pipeline_trace=self.stages,
            editor_actions=list(self._editor_actions),
            final_outcome=final_outcome,
            approval=TraceApproval(
                actor="cli_user@local",
                approved_at=ended_at.isoformat(),
                auto_mode=auto_mode,
            ),
        )
