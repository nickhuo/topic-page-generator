"""Pipeline progress reporter.

Stages call into a `PipelineReporter` to surface what they're doing in
real time. The CLI wires up a `RichReporter` for interactive TTY runs and
a `NullReporter` for `--auto` / non-TTY / tests.

Reporter is intentionally separate from `TraceRecorder`:
- `TraceRecorder` records structured pipeline metrics for `trace.json`.
- `PipelineReporter` is human-facing console output.

Stages take `reporter: PipelineReporter | None = None`; `None` means silent.
"""

from __future__ import annotations

from contextlib import contextmanager
from time import perf_counter
from typing import Any, Iterator, Literal

from rich.console import Console
from rich.live import Live
from rich.table import Table

SectionEvent = Literal[
    "query_generated",
    "pool_grew",
    "eval_satisfied",
    "eval_gaps",
    "cap_hit",
    "extract_started",
    "extract_dropped",
    "extract_ok",
]


class PipelineReporter:
    """No-op base class. Subclasses override to render."""

    @contextmanager
    def stage(self, name: str, *, total: int | None = None) -> Iterator[None]:
        yield

    @contextmanager
    def live_section_table(self, section_ids: list[str]) -> Iterator[None]:
        yield

    def section_event(
        self, section_id: str, event: SectionEvent, **fields: Any
    ) -> None:
        pass

    def note(self, msg: str) -> None:
        pass

    def warn(self, msg: str, **fields: Any) -> None:
        pass


class NullReporter(PipelineReporter):
    """Explicit no-op; identical to base. Kept for clarity at call sites."""


class RichReporter(PipelineReporter):
    """Rich-backed reporter. TTY-friendly; safe on non-TTY (just no Live)."""

    _EVENT_SYMBOL = {
        "query_generated": "?",
        "pool_grew": "+",
        "eval_satisfied": "✓",
        "eval_gaps": "·",
        "cap_hit": "!",
        "extract_started": "·",
        "extract_dropped": "✗",
        "extract_ok": "✓",
    }

    def __init__(self, console: Console) -> None:
        self.console = console
        self._stage_start: float | None = None
        self._stage_name: str | None = None
        # Per-section state for the live table view.
        self._section_state: dict[str, dict[str, Any]] = {}
        self._live: Live | None = None

    # ---------------- stage ----------------
    @contextmanager
    def stage(self, name: str, *, total: int | None = None) -> Iterator[None]:
        self._stage_name = name
        self._stage_start = perf_counter()
        suffix = f" (n={total})" if total is not None else ""
        self.console.print(f"[bold cyan]▸[/bold cyan] {name}{suffix}")
        try:
            yield
        finally:
            elapsed = perf_counter() - (self._stage_start or perf_counter())
            self.console.print(f"[green]✓[/green] {name}  [dim]{elapsed:.1f}s[/dim]")
            self._stage_name = None
            self._stage_start = None

    # ---------------- live section table ----------------
    @contextmanager
    def live_section_table(self, section_ids: list[str]) -> Iterator[None]:
        self._section_state = {
            sid: {"iter": 0, "pool": 0, "status": "queued", "detail": ""}
            for sid in section_ids
        }
        # Only use Live on a real terminal; otherwise fall back to line logs.
        if not self.console.is_terminal:
            yield
            self._section_state = {}
            return

        with Live(
            self._render_table(),
            console=self.console,
            refresh_per_second=8,
            transient=False,
        ) as live:
            self._live = live
            try:
                yield
            finally:
                self._live = None
                self._section_state = {}

    def _render_table(self) -> Table:
        table = Table(show_header=True, header_style="bold", expand=False)
        table.add_column("section", style="bold")
        table.add_column("iter", justify="right")
        table.add_column("pool", justify="right")
        table.add_column("status")
        table.add_column("detail", overflow="ellipsis", max_width=60)
        for sid, st in self._section_state.items():
            table.add_row(
                sid,
                str(st["iter"]),
                str(st["pool"]),
                str(st["status"]),
                str(st["detail"]),
            )
        return table

    # ---------------- events ----------------
    def section_event(
        self, section_id: str, event: SectionEvent, **fields: Any
    ) -> None:
        # Update live table state if we're inside one.
        if section_id in self._section_state:
            st = self._section_state[section_id]
            if event == "query_generated":
                st["iter"] = fields.get("iter", st["iter"])
                st["status"] = "querying"
                st["detail"] = f"q: {fields.get('query', '')}"
            elif event == "pool_grew":
                st["pool"] = fields.get("total", st["pool"])
                st["status"] = "fetched"
                st["detail"] = f"+{fields.get('new', 0)} sources"
            elif event == "eval_satisfied":
                st["status"] = "[green]satisfied[/green]"
                st["detail"] = ""
            elif event == "eval_gaps":
                st["status"] = "gaps"
                gaps = fields.get("gaps") or []
                st["detail"] = "; ".join(gaps[:2])
            elif event == "cap_hit":
                st["status"] = "[yellow]cap_hit[/yellow]"
            elif event == "extract_started":
                st["status"] = "extracting"
            elif event == "extract_dropped":
                st["status"] = "[red]dropped[/red]"
                st["detail"] = f"reason: {fields.get('reason', '?')}"
            elif event == "extract_ok":
                st["status"] = "[green]ok[/green]"
                cites = fields.get("citations")
                if cites is not None:
                    st["detail"] = f"{cites} citations"
            if self._live is not None:
                self._live.update(self._render_table())
            return

        # Outside a live table: emit a single line. Useful for block_extract drops.
        sym = self._EVENT_SYMBOL.get(event, "·")
        color = {
            "extract_dropped": "red",
            "extract_ok": "green",
            "cap_hit": "yellow",
        }.get(event, "dim")
        detail_bits: list[str] = []
        for k, v in fields.items():
            detail_bits.append(f"{k}={v}")
        detail = "  ".join(detail_bits)
        self.console.print(
            f"  [{color}]{sym}[/{color}] {section_id}  [dim]{event}[/dim]  {detail}"
        )

    def note(self, msg: str) -> None:
        self.console.print(f"  [dim]·[/dim] {msg}")

    def warn(self, msg: str, **fields: Any) -> None:
        extra = " ".join(f"{k}={v}" for k, v in fields.items())
        self.console.print(f"  [yellow]![/yellow] {msg} [dim]{extra}[/dim]")


__all__ = ["PipelineReporter", "NullReporter", "RichReporter", "SectionEvent"]
