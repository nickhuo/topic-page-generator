"""Typer CLI entry point.

Commands
--------
``generate run "<sentence>"``  — full editor pipeline.
``generate regen-section <section_id> <data.json>``  — re-run block extraction for one section.

.. note::
   The old bare invocation ``generate "<sentence>"`` no longer works; use
   ``generate run "<sentence>"`` instead.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import typer
from dotenv import load_dotenv
from pydantic import ValidationError
from rich.console import Console

from generator.editor.prompt_cli import EditorPrompter
from generator.llm.client import LLMConfigError, LLMOutputError
from generator.llm.trace_buffer import reset as _reset_llm_calls
from generator.pipeline import ground
from generator.pipeline.render import slugify, subject_from_facts
from generator.pipeline.reporter import NullReporter, RichReporter
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
        help="[DEPRECATED] No-op; plan review is not implemented in the editor architecture.",
    ),
) -> None:
    """Run the editor pipeline on a one-sentence input."""
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
    reporter = (
        RichReporter(console) if (console.is_terminal and not auto) else NullReporter()
    )
    _reset_llm_calls()

    output_paths: dict[str, Any] = {}

    # Trace is flushed incrementally so Ctrl-C / crash still leaves a partial
    # trace.json on disk. Filename starts as page_id; renamed to <slug>.trace.json
    # once we know the slug (post-ground).
    trace_state: dict[str, str] = {"basename": page_id}

    def _flush_trace() -> None:
        try:
            recorder.flush_partial(_OUTPUT_DIR, trace_state["basename"])
        except Exception as exc:  # never let trace flush kill the run
            console.print(f"[dim]trace flush failed: {exc}[/dim]")

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

        # Now that we know the slug, switch the partial-trace filename so the
        # final and partial trace files share a name.
        trace_state["basename"] = slugify(ground_out.canonical_title)
        _flush_trace()

        # Stage 1b: Hero image (best-effort, decorative — never raises).
        from generator.pipeline.hero_image import run_hero_image_stage

        with recorder.stage("hero_image"):
            hero_image = await run_hero_image_stage(ground_out.canonical_title)
            if hero_image:
                console.print(
                    f"[green]✓[/green] Hero image  {hero_image.publisher or 'fetched'}"
                )
            else:
                console.print(
                    "[dim]· Hero image skipped (no Brave key or no results)[/dim]"
                )
        _flush_trace()

        # Editor architecture: planners → research → block_extract → render → deliver
        from generator.pipeline.backbone_planner import build_backbone_sections
        from generator.pipeline.curation_planner import run_curation_stage
        from generator.schema import SectionPlanOutput

        backbone = build_backbone_sections(
            ground_out.facts,
            canonical_title=ground_out.canonical_title or ground_out.facts.what[:80],
        )
        with recorder.stage("curation"):
            curation_out = await run_curation_stage(
                facts=ground_out.facts,
                canonical_title=ground_out.canonical_title
                or ground_out.facts.what[:80],
                backbone=backbone,
                reporter=reporter,
            )
        _flush_trace()

        # HITL: plan_review — let editor prune curated sections before research.
        plan_decision, curated_after_review = prompter.plan_review(
            backbone=backbone,
            curated=list(curation_out.sections),
        )
        if plan_decision == "reject":
            console.print("[bold red]Plan rejected by editor. Stopping.[/bold red]")
            raise typer.Exit(code=5)

        combined = SectionPlanOutput(sections=backbone + curated_after_review)

        # Stage 3: per-section research loop.
        from generator.pipeline.research import run_research_stage
        from generator.sources.wikidata import fetch_wikidata
        from generator.sources.wikipedia import fetch_wikipedia_card

        wd_source, _wd_props = await fetch_wikidata(
            ground_out.facts.entities[0] if ground_out.facts.entities else ""
        )
        _wp_card = await fetch_wikipedia_card(ground_out.canonical_title)
        seed_sources = [wd_source] if wd_source else []

        with recorder.stage("research"):
            with reporter.live_section_table([s.section_id for s in combined.sections]):
                pools = await run_research_stage(
                    sections=combined.sections,
                    canonical_title=ground_out.canonical_title,
                    facts=ground_out.facts,
                    seed_sources=seed_sources,
                    reporter=reporter,
                )
        _flush_trace()

        # Stage 4: block-driven extraction.
        from generator.pipeline.block_extract import run_block_extract_stage

        with recorder.stage("block_extract"):
            rendered_sections = await run_block_extract_stage(
                sections=combined.sections,
                evidence_by_section=pools,
                canonical_title=ground_out.canonical_title,
                entities=ground_out.facts.entities,
                reporter=reporter,
            )
        console.print(
            f"[green]✓[/green] Block extract  sections={len(rendered_sections)}"
        )
        _flush_trace()

        # HITL: sections_review — let editor drop bad sections before render.
        rendered_sections = prompter.sections_review(rendered_sections)
        if not rendered_sections:
            console.print(
                "[bold red]All sections dropped by editor. Stopping.[/bold red]"
            )
            raise typer.Exit(code=5)

        # Stage 5: render.
        from generator.pipeline.render import (
            build_editorial_page,
            render_html,
        )
        from generator.schema import EventLayout, EventMeta

        subject_e = subject_from_facts(ground_out.facts, ground_out.canonical_title)
        all_sources = list({s.id: s for pool in pools.values() for s in pool}.values())

        _now_iso = datetime.now(timezone.utc).isoformat()
        with recorder.stage("render"):
            editorial_page = build_editorial_page(
                input_sentence=sentence,
                page_id=page_id,
                subject=subject_e,
                layout=EventLayout(preset_id="product_focus", overrides=None),
                sources=all_sources + seed_sources,
                editorial_sections=rendered_sections,
                trace_id=recorder.trace_id,
                meta=EventMeta(
                    last_updated=_now_iso,
                    editor_approved=True,
                    editor_id="cli_user@local",
                    pipeline_trace_id=recorder.trace_id,
                ),
                wikipedia_card=_wp_card,
                hero_image=hero_image,
            )
            html = render_html(editorial_page)
            console.print(
                f"[green]✓[/green] Render  sections={len(editorial_page.editorial_sections or [])}"
            )
        _flush_trace()

        # Stage 6: Deliver.
        slug = slugify(ground_out.canonical_title)
        _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        html_path = _OUTPUT_DIR / f"{slug}.html"
        data_path = _OUTPUT_DIR / f"{slug}.data.json"
        trace_path = _OUTPUT_DIR / f"{slug}.trace.json"

        html_path.write_text(html, encoding="utf-8")
        data_path.write_text(editorial_page.model_dump_json(indent=2), encoding="utf-8")

        output_paths["html"] = html_path
        output_paths["data"] = data_path
        output_paths["trace"] = trace_path

        final_decision = prompter.final_approval(html_path)
        final_outcome: str
        if final_decision == "approve":
            final_outcome = "auto_approved" if auto else "approved_published"
        else:
            final_outcome = "rejected"

        trace = recorder.finalize(auto_mode=auto, final_outcome=final_outcome)
        trace_path.write_text(trace.model_dump_json(indent=2), encoding="utf-8")
        console.print(f"[green]✓[/green] Wrote {slug}.html / .data.json / .trace.json")

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
    console.print(f"html:  {output_paths.get('html', '(not written)')}")
    console.print(f"data:  {output_paths.get('data', '(not written)')}")
    console.print(f"trace: {output_paths.get('trace', '(not written)')}")


@app.command("regen-section")
def regen_section(
    section_id: str = typer.Argument(
        ..., help="Section id to regenerate (e.g. 'overview')."
    ),
    data_json_path: Path = typer.Argument(
        ...,
        exists=True,
        readable=True,
        dir_okay=False,
        help="Path to an existing <slug>.data.json file.",
    ),
) -> None:
    """Re-run block extraction for one section against the saved evidence pool."""
    load_dotenv(".env")
    load_dotenv(".env.local", override=True)
    _reset_llm_calls()

    raw = json.loads(data_json_path.read_text(encoding="utf-8"))
    try:
        from generator.schema import EventPage

        page = EventPage.model_validate(raw)
    except ValidationError as exc:
        console.print(f"[bold red]Invalid EventPage:[/bold red] {exc}")
        raise typer.Exit(code=2) from exc

    if page.editorial_sections is None:
        console.print("[bold red]data.json has no editorial_sections.[/bold red]")
        raise typer.Exit(code=2)

    existing = next(
        (s for s in page.editorial_sections if s.section_id == section_id), None
    )
    if existing is None:
        console.print(f"[bold red]Unknown section_id: {section_id}[/bold red]")
        raise typer.Exit(code=1)

    # Reconstruct a SectionPlan stub from the saved RenderedSection.
    from generator.blocks.specs import get_spec
    from generator.schema import SectionPlan

    spec_cls = get_spec(existing.block_kind)
    _backbone_ids = {"overview", "timeline", "media_coverage"}
    stub_section = SectionPlan(
        section_id=existing.section_id,
        kind="curated" if existing.section_id not in _backbone_ids else "backbone",
        title=existing.section_id.replace("_", " ").title(),
        rank=1,
        block_kind=existing.block_kind,
        intent="regen",
        acceptance=spec_cls.default_acceptance,
    )

    # Use the saved sources_used as the evidence pool.
    evidence = existing.sources_used or page.sources

    from generator.pipeline.block_extract import extract_one_section
    from generator.schema import RenderedSection

    async def _do() -> RenderedSection | None:
        return await extract_one_section(
            section=stub_section,
            sources=evidence,
            canonical_title=page.meta.canonical_title
            if hasattr(page.meta, "canonical_title")
            else "",
        )

    new_section = asyncio.run(_do())
    if new_section is None:
        console.print("[bold red]Regen produced no usable section.[/bold red]")
        raise typer.Exit(code=4)

    # Replace in place.
    updated_sections = [
        new_section if s.section_id == section_id else s
        for s in page.editorial_sections
    ]
    updated_page = page.model_copy(update={"editorial_sections": updated_sections})

    data_json_path.write_text(updated_page.model_dump_json(indent=2), encoding="utf-8")

    from generator.pipeline.render import render_html

    slug = data_json_path.stem
    if slug.endswith(".data"):
        slug = slug[: -len(".data")]
    html_path = data_json_path.parent / f"{slug}.html"
    html_path.write_text(render_html(updated_page), encoding="utf-8")

    # Append trace action.
    trace_path = data_json_path.parent / f"{slug}.trace.json"
    if trace_path.exists():
        trace_raw = json.loads(trace_path.read_text(encoding="utf-8"))
        action = {
            "action_at": datetime.now(timezone.utc).isoformat(),
            "actor": "cli_user@local",
            "action": "regenerate_section",
            "target": {"section_id": section_id, "field_path": None},
            "before": None,
            "after": None,
            "reason": "regen-section CLI",
        }
        trace_raw.setdefault("editor_actions", []).append(action)
        trace_path.write_text(json.dumps(trace_raw, indent=2), encoding="utf-8")

    console.print(f"[green]✓[/green] Regenerated section {section_id}")


def main() -> None:
    """Entry point for the `generate` console script."""
    app()


if __name__ == "__main__":
    main()
