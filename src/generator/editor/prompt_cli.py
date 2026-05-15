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
from generator.schema import EditorAction, EventFacts, GroundOutput


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


GroundDecision = Literal["accept", "reject", "retry"]


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
            kind = "accept_module" if output.is_hot_event else "reject_page"
            self._log(
                action=kind,
                target={"module_kind": "ground"},
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
                    action="edit_module_field",
                    target={"module_kind": "ground", "field_path": "input_sentence"},
                    reason="manual_reformulate",
                )
                return "retry", new_sentence.strip()
            self._log(
                action="reject_page",
                target={"module_kind": "ground"},
                reason="manual_reject_not_hot",
            )
            return "reject", output

        # Hot event path — show facts and confirm/edit.
        facts = output.facts
        if facts is None:
            # Should not happen per schema contract, but guard anyway.
            self._log(
                action="reject_page",
                target={"module_kind": "ground"},
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
                    action="accept_module",
                    target={"module_kind": "ground"},
                    reason="manual_accept",
                )
                return "accept", output.model_copy(update={"facts": facts})
            if choice == "n":
                self._log(
                    action="reject_page",
                    target={"module_kind": "ground"},
                    reason="manual_reject_facts",
                )
                return "reject", output
            # Edit path
            edited = self._edit_facts(facts)
            if edited is None:
                continue  # validation failed, loop
            self._log(
                action="edit_module_field",
                target={"module_kind": "ground", "field_path": "facts"},
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
    # 2. plan_review
    # ------------------------------------------------------------------
    def plan_review(self, plan):
        """Editor touchpoint for the needs-driven plan."""
        if self.auto:
            self._log(
                action="accept_module",
                target={"module_kind": "plan"},
                reason="auto_mode",
            )
            return plan

        table = Table(title="Plan Review — Needs Curation")
        table.add_column("Rank", style="bold")
        table.add_column("Need")
        table.add_column("On")
        table.add_column("Section Title")
        table.add_column("Modules")
        table.add_column("Queries")
        for p in sorted(plan.need_plans, key=lambda x: x.rank):
            table.add_row(
                str(p.rank),
                p.need_id,
                "✓" if p.activated else "✗",
                p.section_title[:50],
                ",".join(p.assigned_modules)[:40],
                str(len(p.fetch_queries)),
            )
        self.console.print(table)
        toggle = Prompt.ask(
            "Toggle a need by id (e.g. 'world_reaction'), or enter to accept",
            default="",
        )
        if toggle:
            for p in plan.need_plans:
                if p.need_id == toggle:
                    new_plans = [
                        pp.model_copy(update={"activated": not pp.activated})
                        if pp.need_id == toggle
                        else pp
                        for pp in plan.need_plans
                    ]
                    plan = plan.model_copy(update={"need_plans": new_plans})
                    self._log(
                        action="edit_module_field",
                        target={
                            "module_kind": "plan",
                            "field_path": f"need_plans[{toggle}].activated",
                        },
                        before=p.activated,
                        after=not p.activated,
                        reason="editor toggled need",
                    )
                    break
        return plan

    # ------------------------------------------------------------------
    # 3. module_review
    # ------------------------------------------------------------------
    def module_review(self, module):
        if self.auto:
            self._log(
                action="accept_module",
                target={"module_kind": module.kind},
                reason="auto_mode",
            )
            return ("keep", module)

        while True:
            json_lines = module.model_dump_json(indent=2).splitlines()
            preview = "\n".join(json_lines[:30])
            if len(json_lines) > 30:
                preview += "\n... (truncated)"
            self.console.print(
                Panel(preview, title=f"Module: {module.kind}", expand=False)
            )

            choice = Prompt.ask(
                "[a]ccept / [r]egenerate / [e]dit / [s]kip / [v]iew sources",
                choices=["a", "r", "e", "s", "v"],
                default="a",
            )

            if choice == "a":
                self._log(
                    action="accept_module",
                    target={"module_kind": module.kind},
                    reason="manual_accept",
                )
                return ("keep", module)

            elif choice == "r":
                self._log(
                    action="regenerate_module",
                    target={"module_kind": module.kind},
                    reason="manual_regen",
                )
                return ("regen", module)

            elif choice == "s":
                self._log(
                    action="skip_module",
                    target={"module_kind": module.kind},
                    reason="manual_skip",
                )
                return ("skip", module)

            elif choice == "v":
                conf = module.confidence
                citations = getattr(conf, "citations", None)
                self.console.print(citations if citations is not None else conf)
                # loop again

            elif choice == "e":
                old_module = module
                json_text = module.model_dump_json(indent=2)
                tmp = tempfile.NamedTemporaryFile(
                    suffix=".json", mode="w", delete=False
                )
                tmp.write(json_text)
                tmp.close()
                tmp_path = tmp.name
                subprocess.call([os.environ.get("EDITOR", "vi"), tmp_path])
                with open(tmp_path) as f:
                    new_text = f.read()
                try:
                    new_module = type(module).model_validate_json(new_text)
                except ValidationError as exc:
                    self.console.print(f"[red]Validation error:[/red] {exc}")
                    continue  # loop again, no log
                self._log(
                    action="edit_module_field",
                    target={"module_kind": module.kind},
                    before=old_module.model_dump(),
                    after=new_module.model_dump(),
                    reason="manual_edit",
                )
                return ("keep", new_module)

    # ------------------------------------------------------------------
    # 4. final_approval
    # ------------------------------------------------------------------
    def final_approval(
        self, html_path: str | Path
    ) -> Literal["approve", "reject"] | tuple[Literal["regen"], str]:
        if self.auto:
            self._log(action="approve_page", reason="auto_mode")
            return "approve"

        webbrowser.open(Path(html_path).resolve().as_uri())
        self.console.print("Draft opened in browser. Review the page.")

        while True:
            raw = Prompt.ask("Approve? [y]es / [n]o / [r] <module-kind>")
            raw = raw.strip()
            if raw == "y":
                self._log(action="approve_page", reason="manual_approve")
                return "approve"
            elif raw == "n":
                self._log(action="reject_page", reason="manual_reject")
                return "reject"
            elif raw.startswith("r "):
                kind = raw[2:].strip()
                self._log(
                    action="regenerate_module",
                    target={"module_kind": kind},
                    reason="final_approval_regen",
                )
                return ("regen", kind)
            else:
                self.console.print(
                    "[red]Invalid input.[/red] Enter y, n, or r <module-kind>."
                )
