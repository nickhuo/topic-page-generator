from __future__ import annotations

from datetime import datetime, timezone

from rich.console import Console

from generator.pipeline.trace import TraceRecorder
from generator.schema import EditorAction


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class EditorPrompter:
    def __init__(
        self,
        *,
        auto_mode: bool,
        recorder: TraceRecorder,
        actor: str = "editor:cli",
        console: Console | None = None,
    ) -> None:
        self.auto = auto_mode
        self.rec = recorder
        self.actor = actor
        self.console = console or Console()

    def _log(self, **kw) -> None:
        self.rec.record_editor_action(
            EditorAction(action_at=_now(), actor=self.actor, **kw)
        )

    def triage_review(self, triage, *, confidence: float):
        if confidence >= 0.85:
            return triage
        if self.auto:
            self._log(
                action="accept_module",
                target={"module_kind": "triage"},
                reason="auto_mode",
            )
            return triage
        raise NotImplementedError  # filled in Task 3
