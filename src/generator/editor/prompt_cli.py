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
from rich.prompt import IntPrompt, Prompt
from rich.table import Table

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

    # ------------------------------------------------------------------
    # 1. triage_review
    # ------------------------------------------------------------------
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

        # Interactive path
        alts = triage.alternatives or []
        if not alts:
            return triage

        self.console.print(
            f"[yellow]Low confidence ({confidence:.2f}). Alternatives:[/yellow]"
        )
        for i, alt in enumerate(alts, start=1):
            display = (
                getattr(alt, "label", None) or getattr(alt, "entity", None) or str(alt)
            )
            self.console.print(f"  {i}. {display}")

        pick = IntPrompt.ask("Pick alternative [0 to keep current, 1..N]", default=0)
        if pick == 0:
            return triage

        chosen = alts[pick - 1]
        old_primary = triage.primary_entity
        new_primary = (
            getattr(chosen, "label", None)
            or getattr(chosen, "entity", None)
            or str(chosen)
        )
        triage.primary_entity = new_primary
        self._log(
            action="override_archetype",
            target={"module_kind": "triage"},
            before=old_primary,
            after=new_primary,
            reason="low_confidence_pick",
        )
        return triage

    # ------------------------------------------------------------------
    # 2. disambiguation_review
    # ------------------------------------------------------------------
    def disambiguation_review(self, disamb):
        if self.auto:
            self._log(
                action="accept_module",
                target={"module_kind": "disambiguation"},
                reason="auto_mode",
            )
            return disamb

        candidates = (disamb.unresolved_candidates or [])[:3]
        if not candidates:
            return disamb

        self.console.print("[yellow]Disambiguation needed. Candidates:[/yellow]")
        for i, cand in enumerate(candidates, start=1):
            name = getattr(cand, "entity", None) or str(cand)
            desc = getattr(cand, "rationale", None) or getattr(cand, "description", "")
            self.console.print(f"  {i}. {name} — {desc}")

        pick = IntPrompt.ask("Pick candidate 1..N", default=1)
        chosen = candidates[pick - 1]
        disamb.resolved = True
        disamb.chosen = chosen
        self._log(
            action="accept_module",
            target={"module_kind": "disambiguation"},
            reason="manual_disambiguation",
        )
        return disamb

    # ------------------------------------------------------------------
    # 3. plan_review
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
    # 4. module_review
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
    # 5. final_approval
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
