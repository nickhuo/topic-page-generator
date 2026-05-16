from __future__ import annotations

import os
import subprocess
import tempfile
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from generator.pipeline.trace import TraceRecorder
from generator.schema import (
    EditorAction,
    EventFacts,
    GroundOutput,
    RenderedSection,
    SectionPlan,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


GroundDecision = Literal["accept", "reject", "retry"]


def _preview_for_block(rs: RenderedSection) -> str:
    """Short human-readable preview of a RenderedSection's block_data.

    Pulls the most useful one-liner per block kind. Falls back to a generic
    repr if the data shape is unfamiliar.
    """
    data = rs.block_data
    kind = rs.block_kind
    try:
        if kind == "paragraph":
            text = getattr(data, "text", "") or ""
            first = text.split(". ")[0]
            return (first[:120] + "…") if len(first) > 120 else first
        if kind in ("latest_news", "newsfeed"):
            cards = getattr(data, "cards", None) or []
            return f"{len(cards)} cards"
        if kind == "gallery":
            images = getattr(data, "images", None) or []
            return f"{len(images)} images"
        if kind == "timeline":
            entries = getattr(data, "entries", None) or []
            return f"{len(entries)} entries"
        if kind == "people":
            cards = getattr(data, "cards", None) or []
            names = ", ".join(getattr(c, "name", "?") for c in cards[:3])
            return f"{len(cards)} people: {names}"
        if kind == "reactions":
            quotes = getattr(data, "quotes", None) or []
            return f"{len(quotes)} reactions"
        if kind == "chart":
            return getattr(data, "title", "") or "chart"
    except Exception:
        pass
    return type(data).__name__


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

    # ------------------------------------------------------------------
    # 1. ground_review — gate + fact confirmation
    # ------------------------------------------------------------------
    def ground_review(
        self, output: GroundOutput
    ) -> tuple[GroundDecision, GroundOutput | str]:
        """Editor touchpoint for the ground stage.

        Returns one of:
        - ("accept", GroundOutput): proceed to plan; output.facts may have been edited.
        - ("reject", GroundOutput): not a hot event or user said no; CLI exits 5.
        - ("retry", str): user supplied a reformulated sentence; CLI re-runs ground.
        """
        if self.auto:
            kind = "accept_section" if output.is_hot_event else "reject_page"
            self._log(
                action=kind,
                target={"section_id": "ground"},
                reason="auto_mode",
            )
            decision: GroundDecision = "accept" if output.is_hot_event else "reject"
            return decision, output

        if not output.is_hot_event:
            self.console.print(
                Panel(
                    f"[yellow]Not a hot event.[/yellow]\n\n"
                    f"Reason: {output.rejection_reason or '(no reason given)'}",
                    title="Ground rejected",
                    expand=False,
                )
            )
            choice = Prompt.ask(
                "[r]eformulate sentence / [q]uit",
                choices=["r", "q"],
                default="q",
            )
            if choice == "r":
                new_sentence = Prompt.ask("New sentence")
                self._log(
                    action="edit_section_field",
                    target={"section_id": "ground", "field_path": "input_sentence"},
                    reason="manual_reformulate",
                )
                return "retry", new_sentence.strip()
            self._log(
                action="reject_page",
                target={"section_id": "ground"},
                reason="manual_reject_not_hot",
            )
            return "reject", output

        # Hot event path — show facts and confirm/edit.
        facts = output.facts
        if facts is None:
            # Should not happen per schema contract, but guard anyway.
            self._log(
                action="reject_page",
                target={"section_id": "ground"},
                reason="missing_facts",
            )
            return "reject", output

        while True:
            self._render_facts(facts, output.canonical_title)
            choice = Prompt.ask(
                "[y]es accept / [n]o reject / [e]dit facts",
                choices=["y", "n", "e"],
                default="y",
            )
            if choice == "y":
                self._log(
                    action="accept_section",
                    target={"section_id": "ground"},
                    reason="manual_accept",
                )
                return "accept", output.model_copy(update={"facts": facts})
            if choice == "n":
                self._log(
                    action="reject_page",
                    target={"section_id": "ground"},
                    reason="manual_reject_facts",
                )
                return "reject", output
            # Edit path
            edited = self._edit_facts(facts)
            if edited is None:
                continue  # validation failed, loop
            self._log(
                action="edit_section_field",
                target={"section_id": "ground", "field_path": "facts"},
                before=facts.model_dump(),
                after=edited.model_dump(),
                reason="manual_edit",
            )
            facts = edited

    def _render_facts(self, facts: EventFacts, canonical_title: str | None) -> None:
        table = Table(title=canonical_title or "Event facts", show_header=False)
        table.add_column("Field", style="bold")
        table.add_column("Value")
        table.add_row("entities", ", ".join(facts.entities))
        table.add_row("what", facts.what)
        table.add_row("when", facts.when or "(unknown)")
        table.add_row("where", facts.where or "(unknown)")
        table.add_row("why", facts.why or "(none)")
        table.add_row(
            "supporting_sources",
            ", ".join(facts.supporting_sources) or "(none)",
        )
        self.console.print(table)

    def _edit_facts(self, facts: EventFacts) -> EventFacts | None:
        json_text = facts.model_dump_json(indent=2)
        tmp = tempfile.NamedTemporaryFile(suffix=".json", mode="w", delete=False)
        tmp.write(json_text)
        tmp.close()
        subprocess.call([os.environ.get("EDITOR", "vi"), tmp.name])
        with open(tmp.name) as f:
            new_text = f.read()
        try:
            return EventFacts.model_validate_json(new_text)
        except ValidationError as exc:
            self.console.print(f"[red]Validation error:[/red] {exc}")
            return None

    # ------------------------------------------------------------------
    # 2. plan_review — review curation output before research kicks off.
    # Backbone is read-only (deterministic); curated sections can be dropped
    # to save research budget.
    # ------------------------------------------------------------------
    def plan_review(
        self,
        *,
        backbone: list[SectionPlan],
        curated: list[SectionPlan],
    ) -> tuple[Literal["accept", "reject"], list[SectionPlan]]:
        """Returns ('accept', curated_after_drops) or ('reject', []).

        Backbone is never modified. Caller is responsible for combining
        `backbone + curated_after_drops` before passing to research.
        """
        if self.auto:
            self._log(
                action="accept_section",
                target={"section_id": "plan"},
                reason="auto_mode",
            )
            return "accept", list(curated)

        remaining = list(curated)
        while True:
            self._render_plan(backbone, remaining)
            if not remaining:
                hint = "[a]ccept / [q]uit"
            else:
                hint = "[a]ccept / [d]rop <section_id> / [q]uit"
            choice = Prompt.ask(hint, default="a")
            choice = choice.strip()
            if choice == "a":
                self._log(
                    action="accept_section",
                    target={"section_id": "plan"},
                    reason="manual_accept",
                )
                return "accept", remaining
            if choice == "q":
                self._log(
                    action="reject_page",
                    target={"section_id": "plan"},
                    reason="manual_reject_plan",
                )
                return "reject", []
            if choice.startswith("d "):
                target_id = choice[2:].strip()
                hit = next((s for s in remaining if s.section_id == target_id), None)
                if hit is None:
                    self.console.print(
                        f"[red]No curated section with id '{target_id}'.[/red]"
                    )
                    continue
                remaining = [s for s in remaining if s.section_id != target_id]
                self._log(
                    action="skip_section",
                    target={"section_id": target_id},
                    reason="manual_drop_in_plan_review",
                )
                continue
            self.console.print(
                "[red]Invalid input.[/red] Use 'a', 'q', or 'd <section_id>'."
            )

    def _render_plan(
        self,
        backbone: list[SectionPlan],
        curated: list[SectionPlan],
    ) -> None:
        bt = Table(title="Backbone (read-only)", show_header=True)
        bt.add_column("rank", style="dim", justify="right")
        bt.add_column("section_id", style="dim")
        bt.add_column("title", style="dim")
        bt.add_column("block", style="dim")
        for s in sorted(backbone, key=lambda x: x.rank):
            bt.add_row(str(s.rank), s.section_id, s.title[:50], s.block_kind)
        self.console.print(bt)

        ct = Table(title="Curated (drop with 'd <section_id>')", show_header=True)
        ct.add_column("rank", justify="right")
        ct.add_column("section_id", style="bold")
        ct.add_column("title")
        ct.add_column("block")
        ct.add_column("intent", overflow="ellipsis", max_width=50)
        if not curated:
            ct.add_row("-", "-", "(none — backbone only)", "-", "-")
        else:
            for s in sorted(curated, key=lambda x: x.rank):
                ct.add_row(
                    str(s.rank),
                    s.section_id,
                    s.title[:50],
                    s.block_kind,
                    s.intent,
                )
        self.console.print(ct)

    # ------------------------------------------------------------------
    # 2b. sections_review — after block_extract, before render.
    # Drop any rendered section that looks bad. Regenerate is out of scope
    # for this gate; user is pointed at `generate regen-section` instead.
    # ------------------------------------------------------------------
    def sections_review(self, rendered: list[RenderedSection]) -> list[RenderedSection]:
        if self.auto:
            self._log(
                action="accept_section",
                target={"section_id": "sections"},
                reason="auto_mode",
            )
            return list(rendered)

        remaining = list(rendered)
        while True:
            self._render_sections(remaining)
            choice = Prompt.ask(
                "[a]ccept all / [d]rop <section_id> / [r]egen <section_id>",
                default="a",
            ).strip()
            if choice == "a":
                self._log(
                    action="accept_section",
                    target={"section_id": "sections"},
                    reason="manual_accept",
                )
                return remaining
            if choice.startswith("d "):
                target = choice[2:].strip()
                hit = next((s for s in remaining if s.section_id == target), None)
                if hit is None:
                    self.console.print(f"[red]No section with id '{target}'.[/red]")
                    continue
                remaining = [s for s in remaining if s.section_id != target]
                self._log(
                    action="skip_section",
                    target={"section_id": target},
                    reason="manual_drop_in_sections_review",
                )
                continue
            if choice.startswith("r "):
                target = choice[2:].strip()
                self.console.print(
                    f"[yellow]regen[/yellow] not supported inline. "
                    f"After this run finishes, use: "
                    f"[bold]uv run generate regen-section {target} "
                    "output/<slug>.data.json[/bold]"
                )
                continue
            self.console.print(
                "[red]Invalid input.[/red] Use 'a', 'd <id>', or 'r <id>'."
            )

    def _render_sections(self, rendered: list[RenderedSection]) -> None:
        table = Table(title="Section drafts", show_header=True)
        table.add_column("section_id", style="bold")
        table.add_column("block")
        table.add_column("cites", justify="right")
        table.add_column("preview", overflow="ellipsis", max_width=80)
        for rs in rendered:
            table.add_row(
                rs.section_id,
                rs.block_kind,
                str(len(rs.citations)),
                _preview_for_block(rs),
            )
        self.console.print(table)

    # ------------------------------------------------------------------
    # 3. final_approval
    # ------------------------------------------------------------------
    def final_approval(self, html_path: str | Path) -> Literal["approve", "reject"]:
        if self.auto:
            self._log(action="approve_page", reason="auto_mode")
            return "approve"

        webbrowser.open(Path(html_path).resolve().as_uri())
        self.console.print("Draft opened in browser. Review the page.")

        while True:
            raw = Prompt.ask("Approve? [y]es / [n]o")
            raw = raw.strip()
            if raw == "y":
                self._log(action="approve_page", reason="manual_approve")
                return "approve"
            elif raw == "n":
                self._log(action="reject_page", reason="manual_reject")
                return "reject"
            else:
                self.console.print("[red]Invalid input.[/red] Enter y or n.")
