"""Typer CLI entry point — `generate "<one sentence>"`."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console

from generator.pipeline import consistency, disambiguate, extract, fetch, plan, render, triage
from generator.pipeline.render import slugify
from generator.pipeline.trace import TraceRecorder

console = Console()

_OUTPUT_DIR = Path(__file__).resolve().parents[2] / "output"


def generate(
    sentence: str = typer.Argument(..., help="One-sentence event description."),
    auto: bool = typer.Option(True, "--auto/--interactive", help="Bypass HITL prompts."),
) -> None:
    """Run the 8-stage skeleton on a one-sentence input."""
    console.rule("[bold]topic-page-generator[/bold]")
    console.print(f"[dim]input:[/dim] {sentence}")
    console.print(f"[dim]mode:[/dim] {'auto' if auto else 'interactive'}")

    page_id = f"page_{uuid.uuid4().hex[:8]}"
    recorder = TraceRecorder(sentence, page_id)

    try:
        with recorder.stage("triage", model="stub"):
            triage_out = triage.run(sentence)
            console.print(f"[green]✓[/green] Triage  confidence={triage_out.confidence}")

        slug = slugify(triage_out.primary_entity or sentence)

        with recorder.stage("disambiguate", model="stub"):
            disamb_out = disambiguate.run(triage_out)
            console.print(f"[green]✓[/green] Disambiguate  resolved={disamb_out.resolved}")

        with recorder.stage("plan"):
            plan_out = plan.run_plan(disamb_out)
            console.print(f"[green]✓[/green] Plan  archetype={plan_out.archetype_hint}")

        with recorder.stage("aesthetic_plan", model="stub"):
            aesthetic_out = plan.run_aesthetic(plan_out)
            console.print(
                f"[green]✓[/green] Aesthetic  preset={aesthetic_out.preset_id}"
            )

        with recorder.stage("fetch"):
            sources = fetch.run()
            console.print(f"[green]✓[/green] Fetch  sources={len(sources)}")

        with recorder.stage("extract", model="stub"):
            modules = extract.run(sources)
            console.print(f"[green]✓[/green] Extract  modules={len(modules)}")

        with recorder.stage("consistency", model="stub"):
            consistency_out = consistency.run(modules)
            console.print(
                f"[green]✓[/green] Consistency  passes={consistency_out.passes}"
            )

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
            html_path = _OUTPUT_DIR / f"{slug}.html"
            data_path = _OUTPUT_DIR / f"{slug}.data.json"
            trace_path = _OUTPUT_DIR / f"{slug}.trace.json"

            html_path.write_text(html, encoding="utf-8")
            data_path.write_text(
                page.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
            )
            trace = recorder.finalize(auto_mode=auto)
            trace_path.write_text(
                trace.model_dump_json(indent=2, exclude_none=False), encoding="utf-8"
            )
    except ValidationError as exc:
        console.print("[bold red]Schema validation failed:[/bold red]")
        console.print(json.dumps(exc.errors(), indent=2, default=str))
        raise typer.Exit(code=2) from exc

    console.rule("[bold green]done[/bold green]")
    console.print(f"html:  {html_path}")
    console.print(f"data:  {data_path}")
    console.print(f"trace: {trace_path}")


def app() -> None:
    """Entry point for the `generate` console script."""
    typer.run(generate)


if __name__ == "__main__":
    app()
