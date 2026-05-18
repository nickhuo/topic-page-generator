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

import questionary

from generator.pipeline.trace import TraceRecorder
from generator.schema import (
    EditorAction,
    EditorNotes,
    EventFacts,
    GroundOutput,
    RenderedSection,
    SectionPlan,
    Source,
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
                "(r)eformulate sentence / (q)uit",
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
                "(y)es accept / (n)o reject / (e)dit facts",
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
    async def plan_review(
        self,
        *,
        backbone: list[SectionPlan],
        curated: list[SectionPlan],
        facts: EventFacts | None = None,
        canonical_title: str | None = None,
    ) -> tuple[Literal["accept", "reject"], list[SectionPlan], EditorNotes]:
        """Returns (decision, curated_after_edits, editor_notes).

        Backbone is never modified. Editor can:
          - multi-select sections and either comment on them or (curated only) drop them
          - add a brand-new curated section via natural-language description (LLM)
          - leave a global comment that applies to every section
        """
        if self.auto:
            self._log(
                action="accept_section",
                target={"section_id": "plan"},
                reason="auto_mode",
            )
            return "accept", list(curated), EditorNotes()

        remaining = list(curated)
        section_comments: dict[str, str] = {}
        global_comment: str | None = None

        while True:
            self._render_plan(backbone, remaining)
            if section_comments:
                self.console.print(
                    f"[dim]editor comments so far: "
                    f"{', '.join(section_comments.keys())}[/dim]"
                )
            action = await questionary.select(
                "What next?",
                choices=[
                    "Accept all as-is",
                    "Comment / drop sections",
                    "Add a new section",
                    "Reject plan",
                ],
                default="Accept all as-is",
            ).ask_async()
            if action is None or action == "Reject plan":
                self._log(
                    action="reject_page",
                    target={"section_id": "plan"},
                    reason="manual_reject_plan",
                )
                return "reject", [], EditorNotes()
            if action == "Accept all as-is":
                gc = await questionary.text(
                    "General note that applies to all sections? (blank = none)",
                    multiline=True,
                ).ask_async()
                if gc and gc.strip():
                    global_comment = gc.strip()
                    self._log(
                        action="comment_section",
                        target=None,
                        after={"comment": global_comment, "scope": "global"},
                        reason="manual_global_comment",
                    )
                self._log(
                    action="accept_section",
                    target={"section_id": "plan"},
                    reason="manual_accept",
                )
                return (
                    "accept",
                    remaining,
                    EditorNotes(
                        section_comments=section_comments,
                        global_comment=global_comment,
                    ),
                )
            if action == "Comment / drop sections":
                remaining, section_comments = await self._edit_sections_loop(
                    backbone=backbone,
                    curated=remaining,
                    section_comments=section_comments,
                )
                continue
            if action == "Add a new section":
                if facts is None or canonical_title is None:
                    self.console.print(
                        "[red]Cannot add sections without ground facts; skipping.[/red]"
                    )
                    continue
                new_section = await self._add_section_flow(
                    facts=facts,
                    canonical_title=canonical_title,
                    existing=backbone + remaining,
                )
                if new_section is not None:
                    remaining.append(new_section)
                continue

    async def _edit_sections_loop(
        self,
        *,
        backbone: list[SectionPlan],
        curated: list[SectionPlan],
        section_comments: dict[str, str],
    ) -> tuple[list[SectionPlan], dict[str, str]]:
        all_sections = backbone + curated
        backbone_ids = {s.section_id for s in backbone}
        choices = [
            questionary.Choice(
                title=(
                    f"[{'backbone' if s.section_id in backbone_ids else 'curated'}] "
                    f"{s.section_id} — {s.title[:48]} ({s.block_kind})"
                ),
                value=s.section_id,
            )
            for s in all_sections
        ]
        picked: list[str] | None = await questionary.checkbox(
            "Select sections to comment on or drop (space to toggle, enter to confirm)",
            choices=choices,
        ).ask_async()
        if not picked:
            return curated, section_comments

        remaining = list(curated)
        for section_id in picked:
            is_backbone = section_id in backbone_ids
            action_choices = ["Add / replace comment"]
            if not is_backbone:
                action_choices.append("Drop section")
            action_choices.append("Skip")
            per_action = await questionary.select(
                f"{section_id}:",
                choices=action_choices,
                default="Add / replace comment",
            ).ask_async()
            if per_action is None or per_action == "Skip":
                continue
            if per_action == "Drop section":
                hit = next((s for s in remaining if s.section_id == section_id), None)
                if hit is None:
                    self.console.print(
                        f"[red]No curated section with id '{section_id}'.[/red]"
                    )
                    continue
                remaining = [s for s in remaining if s.section_id != section_id]
                section_comments.pop(section_id, None)
                self._log(
                    action="skip_section",
                    target={"section_id": section_id},
                    reason="manual_drop_in_plan_review",
                )
                continue
            # Add / replace comment
            text = await questionary.text(
                f"Comment for {section_id} (multiline OK, blank to cancel)",
                multiline=True,
            ).ask_async()
            if not text or not text.strip():
                continue
            previous = section_comments.get(section_id)
            section_comments[section_id] = text.strip()
            self._log(
                action="comment_section",
                target={"section_id": section_id},
                before={"comment": previous} if previous else None,
                after={"comment": text.strip()},
                reason="manual_section_comment",
            )
        return remaining, section_comments

    async def _add_section_flow(
        self,
        *,
        facts: EventFacts,
        canonical_title: str,
        existing: list[SectionPlan],
    ) -> SectionPlan | None:
        description = await questionary.text(
            "Describe the new section in one or two sentences (blank to cancel)",
            multiline=True,
        ).ask_async()
        if not description or not description.strip():
            return None
        from generator.pipeline.section_proposer import propose_section

        try:
            with self.rec.stage("section_proposer"):
                proposed = await propose_section(
                    description.strip(),
                    facts=facts,
                    canonical_title=canonical_title,
                    existing_sections=existing,
                )
        except Exception as exc:
            self.console.print(f"[red]Section proposal failed:[/red] {exc}")
            return None

        preview = Table(title=f"Proposed: {proposed.section_id}", show_header=False)
        preview.add_column("field", style="bold")
        preview.add_column("value")
        preview.add_row("title", proposed.title)
        preview.add_row("block_kind", proposed.block_kind)
        preview.add_row("rank", str(proposed.rank))
        preview.add_row("intent", proposed.intent)
        preview.add_row("acceptance", proposed.acceptance.description)
        self.console.print(preview)

        confirmed = await questionary.confirm(
            "Add this section?", default=True
        ).ask_async()
        if not confirmed:
            return None
        self._log(
            action="add_section",
            target={"section_id": proposed.section_id},
            after=proposed.model_dump(),
            reason="manual_add_section",
        )
        return proposed

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

        ct = Table(title="Curated", show_header=True)
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
    # Interactive loop: accept / regenerate / edit+regen / add / drop / reject.
    # ------------------------------------------------------------------
    async def sections_review(
        self,
        *,
        rendered: list[RenderedSection],
        plans: list[SectionPlan],
        pools: dict[str, list[Source]],
        canonical_title: str,
        entities: list[str],
        facts: EventFacts,
        notes: EditorNotes,
        seed_sources: list[Source],
    ) -> tuple[list[RenderedSection], EditorNotes]:
        """Editor review of extracted sections.

        Returns the (possibly-edited) rendered list plus an updated EditorNotes
        carrying any per-section comments captured during regeneration.
        """
        if self.auto:
            self._log(
                action="accept_section",
                target={"section_id": "sections"},
                reason="auto_mode",
            )
            return list(rendered), notes

        remaining = list(rendered)
        plans_by_id: dict[str, SectionPlan] = {p.section_id: p for p in plans}
        pools_by_id: dict[str, list[Source]] = dict(pools)
        section_comments = dict(notes.section_comments)
        global_comment = notes.global_comment

        while True:
            self._render_sections(remaining)
            action = await questionary.select(
                "What next?",
                choices=[
                    "Accept all as-is",
                    "Regenerate a section",
                    "Edit a section (then regenerate)",
                    "Add a new section",
                    "Drop a section",
                    "Reject all",
                ],
                default="Accept all as-is",
            ).ask_async()

            if action is None or action == "Reject all":
                self._log(
                    action="reject_page",
                    target={"section_id": "sections"},
                    reason="manual_reject_sections",
                )
                return [], EditorNotes(
                    section_comments=section_comments,
                    global_comment=global_comment,
                )
            if action == "Accept all as-is":
                self._log(
                    action="accept_section",
                    target={"section_id": "sections"},
                    reason="manual_accept",
                )
                return remaining, EditorNotes(
                    section_comments=section_comments,
                    global_comment=global_comment,
                )
            if action == "Drop a section":
                target = await self._pick_section_id(remaining)
                if target is None:
                    continue
                remaining = [s for s in remaining if s.section_id != target]
                section_comments.pop(target, None)
                self._log(
                    action="skip_section",
                    target={"section_id": target},
                    reason="manual_drop_in_sections_review",
                )
                continue
            if action == "Regenerate a section":
                target = await self._pick_section_id(remaining)
                if target is None:
                    continue
                plan = plans_by_id.get(target)
                if plan is None:
                    self.console.print(
                        f"[red]No plan found for '{target}'.[/red]"
                    )
                    continue
                note = await questionary.text(
                    "Editor note for this regen (blank to skip):",
                    multiline=True,
                ).ask_async()
                if note and note.strip():
                    section_comments[target] = note.strip()
                merged_note = self._merged_note(
                    target, section_comments, global_comment
                )
                regen = await self._regen_section(
                    plan=plan,
                    pool=pools_by_id.get(target, []),
                    canonical_title=canonical_title,
                    entities=entities,
                    editor_note=merged_note,
                )
                if regen is None:
                    self.console.print(
                        f"[red]Regen of '{target}' produced no usable section.[/red]"
                    )
                    continue
                remaining = [regen if s.section_id == target else s for s in remaining]
                self._log(
                    action="regenerate_section",
                    target={"section_id": target},
                    reason="manual_regen_in_sections_review",
                )
                continue
            if action == "Edit a section (then regenerate)":
                target = await self._pick_section_id(remaining)
                if target is None:
                    continue
                plan = plans_by_id.get(target)
                if plan is None:
                    self.console.print(
                        f"[red]No plan found for '{target}'.[/red]"
                    )
                    continue
                edited_plan, note = await self._edit_plan_flow(plan)
                if edited_plan is None:
                    continue
                plans_by_id[target] = edited_plan
                if note:
                    section_comments[target] = note
                merged_note = self._merged_note(
                    target, section_comments, global_comment
                )
                regen = await self._regen_section(
                    plan=edited_plan,
                    pool=pools_by_id.get(target, []),
                    canonical_title=canonical_title,
                    entities=entities,
                    editor_note=merged_note,
                )
                if regen is None:
                    self.console.print(
                        f"[red]Regen of '{target}' produced no usable section.[/red]"
                    )
                    continue
                remaining = [regen if s.section_id == target else s for s in remaining]
                self._log(
                    action="edit_section_field",
                    target={"section_id": target, "field_path": "plan"},
                    before=plan.model_dump(),
                    after=edited_plan.model_dump(),
                    reason="manual_edit_in_sections_review",
                )
                continue
            if action == "Add a new section":
                new_plan = await self._add_section_flow(
                    facts=facts,
                    canonical_title=canonical_title,
                    existing=list(plans_by_id.values()),
                )
                if new_plan is None:
                    continue
                # Research + extract for the new section only.
                new_rs = await self._research_and_extract_one(
                    plan=new_plan,
                    canonical_title=canonical_title,
                    facts=facts,
                    entities=entities,
                    seed_sources=seed_sources,
                    notes=EditorNotes(
                        section_comments=section_comments,
                        global_comment=global_comment,
                    ),
                )
                if new_rs is None:
                    self.console.print(
                        f"[red]New section '{new_plan.section_id}' produced no usable output.[/red]"
                    )
                    continue
                plans_by_id[new_plan.section_id] = new_plan
                pools_by_id[new_plan.section_id] = new_rs.sources_used or []
                remaining.append(new_rs)
                continue

    @staticmethod
    def _merged_note(
        section_id: str,
        section_comments: dict[str, str],
        global_comment: str | None,
    ) -> str | None:
        per = section_comments.get(section_id)
        if per and global_comment:
            return f"{per}\n\nGeneral note: {global_comment}"
        return per or global_comment or None

    async def _pick_section_id(
        self, rendered: list[RenderedSection]
    ) -> str | None:
        if not rendered:
            self.console.print("[red]No sections to pick.[/red]")
            return None
        choice = await questionary.select(
            "Which section?",
            choices=[
                questionary.Choice(
                    title=f"{rs.section_id} ({rs.block_kind})", value=rs.section_id
                )
                for rs in rendered
            ],
        ).ask_async()
        return choice

    async def _edit_plan_flow(
        self, plan: SectionPlan
    ) -> tuple[SectionPlan | None, str | None]:
        new_title = await questionary.text(
            "Title:", default=plan.title
        ).ask_async()
        if new_title is None:
            return None, None
        new_intent = await questionary.text(
            "Intent:", default=plan.intent, multiline=True
        ).ask_async()
        if new_intent is None:
            return None, None
        note = await questionary.text(
            "Editor note for the regen (blank to skip):", multiline=True
        ).ask_async()
        try:
            updated = plan.model_copy(
                update={
                    "title": new_title.strip() or plan.title,
                    "intent": new_intent.strip() or plan.intent,
                }
            )
        except ValidationError as exc:
            self.console.print(f"[red]Invalid edit:[/red] {exc}")
            return None, None
        return updated, (note.strip() if note and note.strip() else None)

    async def _regen_section(
        self,
        *,
        plan: SectionPlan,
        pool: list[Source],
        canonical_title: str,
        entities: list[str],
        editor_note: str | None,
    ) -> RenderedSection | None:
        from generator.pipeline.block_extract import extract_one_section

        with self.rec.stage(f"regen:{plan.section_id}"):
            return await extract_one_section(
                section=plan,
                sources=pool,
                canonical_title=canonical_title,
                entities=entities,
                editor_note=editor_note,
            )

    async def _research_and_extract_one(
        self,
        *,
        plan: SectionPlan,
        canonical_title: str,
        facts: EventFacts,
        entities: list[str],
        seed_sources: list[Source],
        notes: EditorNotes,
    ) -> RenderedSection | None:
        from generator.pipeline.block_extract import extract_one_section
        from generator.pipeline.research import run_research_stage

        try:
            with self.rec.stage(f"research:{plan.section_id}"):
                pools = await run_research_stage(
                    sections=[plan],
                    canonical_title=canonical_title,
                    facts=facts,
                    seed_sources=seed_sources,
                    notes=notes,
                )
        except Exception as exc:
            self.console.print(f"[red]Research failed:[/red] {exc}")
            return None
        pool = pools.get(plan.section_id, [])
        with self.rec.stage(f"extract:{plan.section_id}"):
            return await extract_one_section(
                section=plan,
                sources=pool,
                canonical_title=canonical_title,
                entities=entities,
                editor_note=self._merged_note(
                    plan.section_id, notes.section_comments, notes.global_comment
                ),
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
            raw = Prompt.ask("Approve? (y)es / (n)o")
            raw = raw.strip()
            if raw == "y":
                self._log(action="approve_page", reason="manual_approve")
                return "approve"
            elif raw == "n":
                self._log(action="reject_page", reason="manual_reject")
                return "reject"
            else:
                self.console.print("[red]Invalid input.[/red] Enter y or n.")
