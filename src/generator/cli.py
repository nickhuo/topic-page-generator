"""Typer CLI entry point.

Commands
--------
``generate run "<sentence>"``  — full 7-stage pipeline (was the only command).
``generate regen-module <kind> <data.json>``  — re-run module extraction.

.. note::
   The old bare invocation ``generate "<sentence>"`` no longer works; use
   ``generate run "<sentence>"`` instead.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import typer
from dotenv import load_dotenv
from pydantic import ValidationError
from rich.console import Console

from generator.editor.prompt_cli import EditorPrompter, _now
from generator.llm.client import LLMConfigError, LLMOutputError
from generator.llm.trace_buffer import reset as _reset_llm_calls
from generator.modules.base import PlanContext
from generator.pipeline import consistency, extract, ground, plan, render
from generator.pipeline.extract import extract_one_module
from generator.pipeline.fetch import EmptyEvidencePoolError, run_fetch_stage
from generator.pipeline.render import slugify, subject_from_facts
from generator.pipeline.trace import TraceRecorder

console = Console()

app = typer.Typer(no_args_is_help=True)

_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


@app.command("run")
def generate(
    sentence: str = typer.Argument(..., help="One-sentence event description."),
    auto: bool = typer.Option(
        False, "--auto", help="Bypass HITL prompts; auto-accept all defaults."
    ),
    review_plan: bool = typer.Option(
        False,
        "--review-plan",
        help="Enable the optional plan-override HITL touchpoint.",
    ),
) -> None:
    """Run the 7-stage pipeline on a one-sentence input."""
    # Load .env files so OPENROUTER_API_KEY / TAVILY_API_KEY / MODEL_* overrides
    # don't have to be exported in every shell. .env.local wins over .env.
    load_dotenv(".env")
    load_dotenv(".env.local", override=True)

    console.rule("[bold]topic-page-generator[/bold]")
    console.print(f"[dim]input:[/dim] {sentence}")
    console.print(f"[dim]mode:[/dim] {'auto' if auto else 'interactive'}")

    page_id = f"page_{uuid.uuid4().hex[:8]}"
    recorder = TraceRecorder(sentence, page_id)
    prompter = EditorPrompter(auto_mode=auto, recorder=recorder)
    _reset_llm_calls()

    output_paths: dict[str, Any] = {}

    async def _run() -> None:
        # Stage 1: Ground (with optional reformulation loop).
        current_sentence = sentence
        while True:
            with recorder.stage("ground"):
                ground_out = await ground.run(current_sentence)
                console.print(
                    f"[green]✓[/green] Ground  is_hot_event={ground_out.is_hot_event} "
                    f"confidence={ground_out.confidence}"
                )

            decision, payload = prompter.ground_review(ground_out)
            if decision == "retry" and isinstance(payload, str):
                current_sentence = payload
                console.print(f"[dim]retrying with:[/dim] {current_sentence}")
                continue
            if decision == "reject" or not ground_out.is_hot_event:
                console.print(
                    "[bold red]Stopping:[/bold red] not an unfolding hot event."
                )
                if ground_out.rejection_reason:
                    console.print(f"  reason: {ground_out.rejection_reason}")
                raise typer.Exit(code=5)
            # decision == "accept"
            assert isinstance(payload, type(ground_out))  # for type narrowing
            ground_out = payload
            break

        if ground_out.facts is None or not ground_out.canonical_title:
            console.print("[bold red]Ground returned no facts. Aborting.[/bold red]")
            raise typer.Exit(code=4)

        subject = subject_from_facts(ground_out.facts, ground_out.canonical_title)
        slug = slugify(ground_out.canonical_title)

        # Stage 2a: Plan.
        with recorder.stage("plan"):
            need_plan_out = await plan.run_plan_stage(
                ground_out.facts, ground_out.canonical_title
            )
            activated = [p for p in need_plan_out.need_plans if p.activated]
            console.print(
                f"[green]✓[/green] Plan  activated_needs={len(activated)}/8 "
                f"preset={need_plan_out.layout_preset_id}"
            )

        if review_plan:
            need_plan_out = prompter.plan_review(need_plan_out)

        # Stage 3: Fetch.
        try:
            with recorder.stage("fetch"):
                sources = await run_fetch_stage(need_plan_out, subject)
        except EmptyEvidencePoolError as exc:
            console.print(f"[bold red]Fetch failed:[/bold red] {exc}")
            raise typer.Exit(code=3) from exc
        except httpx.HTTPError as exc:
            console.print(f"[bold red]Network error during fetch:[/bold red] {exc}")
            raise typer.Exit(code=3) from exc

        console.print(f"[green]✓[/green] Fetch  sources={len(sources)}")

        # Build a small evidence preview to pass into the aesthetic prompt.
        evidence_preview = "\n".join(
            f"- {s.publisher.tier} {s.publisher.name}: {s.title}" for s in sources[:6]
        )

        # Stage 2b: Aesthetic.
        with recorder.stage("aesthetic_plan"):
            aesthetic_out = await plan.run_aesthetic_stage(
                ground_out.facts,
                ground_out.canonical_title,
                need_plan_out,
                evidence_preview,
            )
            console.print(
                f"[green]✓[/green] Aesthetic  preset={aesthetic_out.preset_id}"
            )

        # Stage 4: Extract.
        with recorder.stage("extract"):
            modules = await extract.run(need_plan_out, aesthetic_out, subject, sources)
            console.print(f"[green]✓[/green] Extract  modules={len(modules)}")

        # Stage 5: Consistency.
        with recorder.stage("consistency"):
            ctx = PlanContext(
                subject=subject, need_plan=need_plan_out, aesthetic=aesthetic_out
            )
            consistency_out, modules, needs_coverage, uncovered = await consistency.run(
                modules, ctx, sources
            )
            console.print(
                f"[green]✓[/green] Consistency  passes={consistency_out.passes}"
            )

        # Module review touchpoint.
        reviewed: list = []
        for m in modules:
            needs_review = getattr(m.confidence, "overall", 1.0) < 0.80 or bool(
                getattr(m.confidence, "flags", [])
            )
            if not needs_review:
                reviewed.append(m)
                continue
            verdict, m2 = prompter.module_review(m)
            if verdict == "regen":
                from generator.pipeline.extract import _filter_evidence

                evidence = _filter_evidence(sources, need_plan_out)
                m2_regenned = await extract_one_module(
                    m2,
                    ctx,
                    evidence,
                    regen_feedback="editor requested regeneration via CLI prompt",
                )
                if m2_regenned is not None:
                    reviewed.append(m2_regenned)
                else:
                    reviewed.append(m2)
            elif verdict == "skip":
                continue  # drop the module
            else:  # "keep"
                reviewed.append(m2)
        modules = reviewed

        # Stage 6: Render.
        with recorder.stage("render"):
            page = render.build_page(
                input_sentence=sentence,
                page_id=page_id,
                subject=subject,
                aesthetic=aesthetic_out,
                sources=sources,
                modules=modules,
                trace_id=recorder.trace_id,
                needs_coverage=needs_coverage,
                uncovered_needs=uncovered,
                need_plans=need_plan_out.need_plans,
            )
            html = render.render_html(page)
            console.print(
                f"[green]✓[/green] Render  modules_in_page={len(page.modules)}"
            )

        # Stage 7: Deliver.
        with recorder.stage("deliver"):
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_paths["html"] = _OUTPUT_DIR / f"{slug}.html"
            output_paths["data"] = _OUTPUT_DIR / f"{slug}.data.json"
            output_paths["trace"] = _OUTPUT_DIR / f"{slug}.trace.json"

            output_paths["html"].write_text(html, encoding="utf-8")
            output_paths["data"].write_text(
                page.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
            )

            # Final approval touchpoint
            verdict = prompter.final_approval(output_paths["html"])
            final_outcome: str
            if verdict == "approve":
                final_outcome = "auto_approved" if auto else "approved_published"
            elif verdict == "reject":
                final_outcome = "rejected"
            elif isinstance(verdict, tuple) and verdict[0] == "regen":
                regen_kind = verdict[1]
                target_idx = next(
                    (i for i, m in enumerate(modules) if m.kind == regen_kind), None
                )
                if target_idx is not None:
                    from generator.pipeline.extract import _filter_evidence

                    evidence = _filter_evidence(sources, need_plan_out)
                    regenned = await extract_one_module(
                        modules[target_idx],
                        ctx,
                        evidence,
                        regen_feedback=f"final-approval regen for {regen_kind}",
                    )
                    if regenned is not None:
                        modules[target_idx] = regenned
                    # Re-render
                    page = render.build_page(
                        input_sentence=sentence,
                        page_id=page_id,
                        subject=subject,
                        aesthetic=aesthetic_out,
                        sources=sources,
                        modules=modules,
                        trace_id=recorder.trace_id,
                        needs_coverage=needs_coverage,
                        uncovered_needs=uncovered,
                        need_plans=need_plan_out.need_plans,
                    )
                    output_paths["html"].write_text(
                        render.render_html(page), encoding="utf-8"
                    )
                    output_paths["data"].write_text(
                        page.model_dump_json(indent=2, exclude_none=False),
                        encoding="utf-8",
                    )
                final_outcome = "draft_saved"
            else:
                final_outcome = "draft_saved"

            trace = recorder.finalize(auto_mode=auto, final_outcome=final_outcome)
            output_paths["trace"].write_text(
                trace.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
            )

    try:
        asyncio.run(_run())
    except typer.Exit:
        raise
    except LLMConfigError as exc:
        console.print(f"[bold red]LLM configuration error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    except LLMOutputError as exc:
        console.print(f"[bold red]LLM returned invalid output:[/bold red] {exc}")
        raise typer.Exit(code=4) from exc
    except httpx.HTTPError as exc:
        # Tenacity exhausted retries for a transient LLM-side failure (sustained
        # 429/5xx or network outage). Convert to a clean exit instead of a stack trace.
        console.print(f"[bold red]Network error calling LLM:[/bold red] {exc}")
        raise typer.Exit(code=3) from exc
    except ValidationError as exc:
        console.print("[bold red]Schema validation failed:[/bold red]")
        console.print(json.dumps(exc.errors(), indent=2, default=str))
        raise typer.Exit(code=2) from exc

    console.rule("[bold green]done[/bold green]")
    console.print(f"html:  {output_paths['html']}")
    console.print(f"data:  {output_paths['data']}")
    console.print(f"trace: {output_paths['trace']}")


@app.command("regen-module")
def regen_module(
    kind: str = typer.Argument(
        ..., help="Module kind to regenerate (e.g. 'reactions')."
    ),
    data_json_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        dir_okay=False,
        help="Path to an existing <slug>.data.json file.",
    ),
) -> None:
    """Re-run module extraction for one module against the cached evidence pool."""
    from generator.modules import MODULE_REGISTRY, all_modules  # noqa: F401 — populates registry
    from generator.pipeline.extract import _filter_evidence
    from generator.pipeline.render import render_html
    from generator.schema import (
        AestheticOverrides,
        AestheticPlanOutput,
        EditorAction,
        EditorActionTarget,
        EventPage,
        NeedCurationPlan,
        NeedPlanOutput,
        TierQuota,
        Trace,
    )

    # ------------------------------------------------------------------ load
    page = EventPage.model_validate_json(data_json_path.read_text())

    target_typed = next((m for m in page.modules if m.kind == kind), None)
    if target_typed is None:
        typer.echo(f"No module with kind '{kind}' in {data_json_path}", err=True)
        raise typer.Exit(1)

    # Instantiate the bare Module class (needed by extract_one_module).
    all_modules()  # populate registry
    ModuleCls = MODULE_REGISTRY.get(kind)
    if ModuleCls is None:
        typer.echo(f"Unknown module kind '{kind}'.", err=True)
        raise typer.Exit(1)
    module_instance = ModuleCls()

    # ------------------------------------------------------------------ rebuild PlanContext
    if page.need_plans:
        need_plan_stub = NeedPlanOutput(
            need_plans=list(page.need_plans),
            layout_preset_id=page.layout.preset_id,
        )
    else:
        all_kinds = [m.kind for m in page.modules]
        all_need_ids = (
            "what_happened",
            "when_where",
            "who_involved",
            "current_state",
            "why_matters",
            "world_reaction",
            "what_can_do",
            "what_next",
        )
        need_plan_stub = NeedPlanOutput(
            need_plans=[
                NeedCurationPlan(
                    need_id=nid,
                    activated=(idx == 0),
                    rank=idx + 1,
                    section_title="(regen stub)",
                    rationale="reconstructed for regen-module CLI",
                    fetch_queries=[],
                    assigned_modules=all_kinds if idx == 0 else [],
                    render_overrides={},
                    publisher_quota=TierQuota(),
                )
                for idx, nid in enumerate(all_need_ids)
            ],
            layout_preset_id=page.layout.preset_id,
        )
    aesthetic_stub = AestheticPlanOutput(
        preset_id=page.layout.preset_id,
        preset_confidence=1.0,
        alternatives_considered=[],
        aesthetic_overrides=AestheticOverrides(),
        reasoning="reconstructed for regen-module CLI",
    )
    ctx = PlanContext(
        subject=page.subject, need_plan=need_plan_stub, aesthetic=aesthetic_stub
    )

    # ------------------------------------------------------------------ extract
    evidence = _filter_evidence(page.sources, need_plan_stub)

    new_typed = asyncio.run(
        extract_one_module(
            module_instance,
            ctx,
            evidence,
            regen_feedback="manual regen via CLI subcommand",
        )
    )
    if new_typed is None:
        typer.echo(
            f"Extraction returned None for module '{kind}' — keeping original.",
            err=True,
        )
        raise typer.Exit(2)

    # ------------------------------------------------------------------ update page
    updated_modules = [new_typed if m.kind == kind else m for m in page.modules]
    from datetime import datetime, timezone

    from generator.schema import EventMeta

    now_iso = datetime.now(timezone.utc).isoformat()
    updated_page = EventPage(
        page_id=page.page_id,
        input_sentence=page.input_sentence,
        generated_at=page.generated_at,
        subject=page.subject,
        modules=updated_modules,
        layout=page.layout,
        sources=page.sources,
        needs_coverage=page.needs_coverage,
        uncovered_needs=page.uncovered_needs,
        need_plans=page.need_plans,
        meta=EventMeta(
            last_updated=now_iso,
            editor_approved=page.meta.editor_approved,
            editor_id=page.meta.editor_id,
            pipeline_trace_id=page.meta.pipeline_trace_id,
        ),
    )
    data_json_path.write_text(
        updated_page.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
    )

    # ------------------------------------------------------------------ re-render HTML
    html_path = data_json_path.parent / (
        data_json_path.name.removesuffix(".data.json") + ".html"
    )
    html_path.write_text(render_html(updated_page), encoding="utf-8")

    # ------------------------------------------------------------------ append trace action
    trace_path = data_json_path.parent / (
        data_json_path.name.removesuffix(".data.json") + ".trace.json"
    )
    if trace_path.exists():
        trace_obj = Trace.model_validate_json(trace_path.read_text())
        action = EditorAction(
            action_at=_now(),
            actor="editor:cli",
            action="regenerate_module",
            target=EditorActionTarget(module_kind=kind),
            reason="cli regen-module subcommand",
        )
        # Trace is frozen; rebuild with the appended action.
        updated_trace = Trace(
            **{
                **trace_obj.model_dump(),
                "editor_actions": [
                    *[a.model_dump() for a in trace_obj.editor_actions],
                    action.model_dump(),
                ],
            }
        )
        trace_path.write_text(
            updated_trace.model_dump_json(indent=2, exclude_none=False),
            encoding="utf-8",
        )

    typer.echo(f"Regenerated module '{kind}' in {data_json_path}.")


def main() -> None:
    """Entry point for the `generate` console script."""
    app()


if __name__ == "__main__":
    main()
