"""Typer CLI entry point.

Commands
--------
``generate run "<sentence>"``  — full 8-stage pipeline (was the only command).
``generate regen-module <kind> <data.json>``  — re-run Stage 5 for one module.

.. note::
   The old bare invocation ``generate "<sentence>"`` no longer works; use
   ``generate run "<sentence>"`` instead.  The README will be updated in Task 7.
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
from generator.pipeline import consistency, disambiguate, extract, plan, render, triage
from generator.pipeline.extract import extract_one_module
from generator.pipeline.fetch import EmptyEvidencePoolError, run_fetch_stage
from generator.pipeline.render import slugify
from generator.pipeline.trace import TraceRecorder
from generator.schema import EventSubject, TriageOutput

console = Console()

app = typer.Typer(no_args_is_help=True)

_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


def _subject_from_triage(t: TriageOutput) -> EventSubject:
    return EventSubject(
        primary_entity=t.primary_entity or "Unknown",
        event_type_hint=t.event_type_hint or "generic",
        temporal_posture=t.temporal_posture or "recent",
        time_anchor=t.time_anchor,
    )


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
    """Run the 8-stage pipeline on a one-sentence input."""
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
        with recorder.stage("triage"):
            triage_out = await triage.run(sentence)
            console.print(
                f"[green]✓[/green] Triage  confidence={triage_out.confidence}"
            )

        triage_out = prompter.triage_review(
            triage_out, confidence=triage_out.confidence
        )

        slug = slugify(triage_out.primary_entity or sentence)

        with recorder.stage("disambiguate"):
            disamb_out = await disambiguate.run(triage_out)
            console.print(
                f"[green]✓[/green] Disambiguate  resolved={disamb_out.resolved}"
            )

        if not disamb_out.resolved:
            disamb_out = prompter.disambiguation_review(disamb_out)

        with recorder.stage("plan"):
            plan_out = plan.run_plan_stage(triage_out, disamb_out)
            console.print(f"[green]✓[/green] Plan  archetype={plan_out.archetype_hint}")

        if review_plan:
            plan_out = prompter.plan_review(plan_out)

        try:
            with recorder.stage("fetch"):
                sources = await run_fetch_stage(
                    plan_out, _subject_from_triage(triage_out)
                )
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

        with recorder.stage("aesthetic_plan"):
            aesthetic_out = await plan.run_aesthetic_stage(
                triage_out, plan_out, evidence_preview
            )
            console.print(
                f"[green]✓[/green] Aesthetic  preset={aesthetic_out.preset_id}"
            )

        subject = _subject_from_triage(triage_out)

        with recorder.stage("extract"):
            modules = await extract.run(plan_out, aesthetic_out, subject, sources)
            console.print(f"[green]✓[/green] Extract  modules={len(modules)}")

        with recorder.stage("consistency"):
            ctx = PlanContext(subject=subject, plan=plan_out, aesthetic=aesthetic_out)
            consistency_out, modules, needs_coverage, uncovered = await consistency.run(
                modules, ctx, sources
            )
            console.print(
                f"[green]✓[/green] Consistency  passes={consistency_out.passes}"
            )

        # Stage 5 module review touchpoint
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

                evidence = _filter_evidence(sources, plan_out)
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

        with recorder.stage("render"):
            page = render.build_page(
                input_sentence=sentence,
                page_id=page_id,
                triage=triage_out,
                aesthetic=aesthetic_out,
                sources=sources,
                modules=modules,
                trace_id=recorder.trace_id,
                needs_coverage=needs_coverage,
                uncovered_needs=uncovered,
            )
            html = render.render_html(page)
            console.print(
                f"[green]✓[/green] Render  modules_in_page={len(page.modules)}"
            )

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

                    evidence = _filter_evidence(sources, plan_out)
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
                        triage=triage_out,
                        aesthetic=aesthetic_out,
                        sources=sources,
                        modules=modules,
                        trace_id=recorder.trace_id,
                        needs_coverage=needs_coverage,
                        uncovered_needs=uncovered,
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
    """Re-run Stage 5 for one module against the cached evidence pool."""
    from generator.modules import MODULE_REGISTRY, all_modules  # noqa: F401 — populates registry
    from generator.schema import (
        AestheticOverrides,
        AestheticPlanOutput,
        EditorAction,
        EditorActionTarget,
        EventPage,
        PlanComposition,
        PlanOutput,
        SourceStrategy,
        Trace,
    )
    from generator.pipeline.extract import _filter_evidence
    from generator.pipeline.render import render_html

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
    # EventPage doesn't store PlanOutput/AestheticPlanOutput directly; reconstruct
    # minimal stubs from the data that IS available on the page.
    composition = [
        PlanComposition(
            module_kind=m.kind,
            artifact=m.artifact,
            slot=m.slot,
            priority=m.inclusion_reason,
            artifact_alternatives=m.artifact_alternatives,
        )
        for m in page.modules
    ]
    # Reconstruct a source strategy from the actual sources present.
    tiers_present = list({s.publisher.tier for s in page.sources})
    plan_stub = PlanOutput(
        archetype_hint="regen",
        layout_preset_id=page.layout.preset_id,
        composition=composition,
        source_strategy=SourceStrategy(
            preferred_tiers=tiers_present or ["T0", "T1", "T2", "T3"],
            time_range_days=365,
            min_publishers=1,
        ),
    )
    aesthetic_stub = AestheticPlanOutput(
        preset_id=page.layout.preset_id,
        preset_confidence=1.0,
        alternatives_considered=[],
        aesthetic_overrides=AestheticOverrides(),
        reasoning="reconstructed for regen-module CLI",
    )
    ctx = PlanContext(subject=page.subject, plan=plan_stub, aesthetic=aesthetic_stub)

    # ------------------------------------------------------------------ extract
    evidence = _filter_evidence(page.sources, plan_stub)

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
    # Build a fresh EventPage preserving all existing metadata.
    from generator.schema import EventMeta
    from datetime import datetime, timezone

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
