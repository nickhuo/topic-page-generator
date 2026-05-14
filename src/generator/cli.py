"""Typer CLI entry point — `generate "<one sentence>"`."""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any

import httpx
import typer
from pydantic import ValidationError
from rich.console import Console

from generator.llm.client import LLMConfigError
from generator.llm.trace_buffer import reset as _reset_llm_calls
from generator.pipeline import consistency, disambiguate, extract, plan, render, triage
from generator.pipeline.fetch import EmptyEvidencePoolError, run_fetch_stage
from generator.pipeline.render import slugify
from generator.pipeline.trace import TraceRecorder
from generator.schema import EventSubject, TriageOutput

console = Console()

_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


def _subject_from_triage(t: TriageOutput) -> EventSubject:
    return EventSubject(
        primary_entity=t.primary_entity or "Unknown",
        event_type_hint=t.event_type_hint or "generic",
        temporal_posture=t.temporal_posture or "recent",
        time_anchor=t.time_anchor,
    )


def generate(
    sentence: str = typer.Argument(..., help="One-sentence event description."),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Bypass HITL prompts."),
) -> None:
    """Run the 8-stage pipeline on a one-sentence input."""
    console.rule("[bold]topic-page-generator[/bold]")
    console.print(f"[dim]input:[/dim] {sentence}")
    console.print(f"[dim]mode:[/dim] {'auto' if auto else 'interactive'}")

    page_id = f"page_{uuid.uuid4().hex[:8]}"
    recorder = TraceRecorder(sentence, page_id)
    _reset_llm_calls()

    output_paths: dict[str, Any] = {}

    async def _run() -> None:
        with recorder.stage("triage"):
            triage_out = await triage.run(sentence)
            console.print(f"[green]✓[/green] Triage  confidence={triage_out.confidence}")

        slug = slugify(triage_out.primary_entity or sentence)

        with recorder.stage("disambiguate"):
            disamb_out = await disambiguate.run(triage_out)
            console.print(f"[green]✓[/green] Disambiguate  resolved={disamb_out.resolved}")

        with recorder.stage("plan"):
            plan_out = plan.run_plan_stage(triage_out, disamb_out)
            console.print(f"[green]✓[/green] Plan  archetype={plan_out.archetype_hint}")

        with recorder.stage("fetch"):
            try:
                sources = await run_fetch_stage(plan_out, _subject_from_triage(triage_out))
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
            aesthetic_out = await plan.run_aesthetic_stage(triage_out, plan_out, evidence_preview)
            console.print(f"[green]✓[/green] Aesthetic  preset={aesthetic_out.preset_id}")

        with recorder.stage("extract", model="stub"):
            modules = extract.run(sources)
            console.print(f"[green]✓[/green] Extract  modules={len(modules)}")

        with recorder.stage("consistency", model="stub"):
            consistency_out = consistency.run(modules)
            console.print(f"[green]✓[/green] Consistency  passes={consistency_out.passes}")

        with recorder.stage("render"):
            page = render.build_page(
                input_sentence=sentence,
                page_id=page_id,
                triage=triage_out,
                aesthetic=aesthetic_out,
                sources=sources,
                modules=modules,
                trace_id=recorder.trace_id,
            )
            html = render.render_html(page)
            console.print(f"[green]✓[/green] Render  modules_in_page={len(page.modules)}")

        with recorder.stage("deliver"):
            _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            output_paths["html"] = _OUTPUT_DIR / f"{slug}.html"
            output_paths["data"] = _OUTPUT_DIR / f"{slug}.data.json"
            output_paths["trace"] = _OUTPUT_DIR / f"{slug}.trace.json"

            output_paths["html"].write_text(html, encoding="utf-8")
            output_paths["data"].write_text(
                page.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
            )
            trace = recorder.finalize(auto_mode=auto)
            output_paths["trace"].write_text(
                trace.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
            )

    try:
        asyncio.run(_run())
    except LLMConfigError as exc:
        console.print(f"[bold red]LLM configuration error:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc
    except ValidationError as exc:
        console.print("[bold red]Schema validation failed:[/bold red]")
        console.print(json.dumps(exc.errors(), indent=2, default=str))
        raise typer.Exit(code=2) from exc

    console.rule("[bold green]done[/bold green]")
    console.print(f"html:  {output_paths['html']}")
    console.print(f"data:  {output_paths['data']}")
    console.print(f"trace: {output_paths['trace']}")


def app() -> None:
    """Entry point for the `generate` console script."""
    typer.run(generate)


if __name__ == "__main__":
    app()
