"""Analysis pipeline: orchestrates technique execution, artifact writing, and synthesis.

@decision DEC-PIPE-001: Sequential execution with prior-results threading.
Techniques run sequentially because later techniques depend on earlier results
(e.g., ACH uses assumptions, indicators uses ACH hypotheses). Each technique
receives the accumulated prior_results dict. Rich progress display shows
real-time status. The pipeline catches per-technique errors gracefully so a
single failure doesn't abort the entire run.

@decision DEC-PIPE-002
@title EventBus integration for pipeline progress visibility
@status accepted
@rationale The research phase previously ran inside a console.status() spinner,
which suppressed all intermediate output. Replacing it with event emissions lets
callers subscribe Rich handlers (or any async handler) for real-time progress.
The console.status() spinner is removed from the research phase so that
handler-printed lines appear immediately. The spinner is retained for
technique-selection (fast, no intermediate steps to show).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sat.providers.rate_limiter import ProviderRateLimiter

from pydantic import ValidationError
from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from sat.artifacts import ArtifactWriter
from sat.config import AnalysisConfig
from sat.errors import is_transient_error
from sat.events import (
    ArtifactWritten,
    EventBus,
    PipelineEvent,
    ProviderCompleted,
    ProviderFailed,
    ResearchCompleted,
    ResearchStarted,
    StageCompleted,
    StageStarted,
)
from sat.models.base import ArtifactResult
from sat.prompts.base import format_research_evidence
from sat.providers.registry import create_provider
from sat.techniques.base import TechniqueContext
from sat.techniques.registry import get_technique
from sat.techniques.selector import select_techniques
from sat.techniques.synthesis import run_synthesis

# Adversarial imports (lazy at usage site for optional dependency)
# from sat.adversarial.pool import ProviderPool
# from sat.adversarial.session import AdversarialSession

logger = logging.getLogger(__name__)
console = Console()


class RichProgressHandler:
    """Renders pipeline events as Rich console output.

    Subscribes to an EventBus and prints human-friendly progress lines
    for each event type. Used by run_analysis() to give real-time
    visibility into the research phase and artifact writes.
    """

    def __init__(self, console: Console) -> None:
        self._console = console

    async def __call__(self, event: PipelineEvent) -> None:
        if isinstance(event, ResearchStarted):
            names = ", ".join(event.provider_names)
            self._console.print(
                f"  [dim]Querying {len(event.provider_names)} provider(s): {names}[/dim]"
            )
        elif isinstance(event, ProviderCompleted):
            self._console.print(
                f"  [green]✓[/green] {event.name}: {event.citation_count} citations"
            )
        elif isinstance(event, ProviderFailed):
            label = "[yellow]⚠ transient[/yellow]" if event.transient else "[red]✗[/red]"
            self._console.print(f"  {label} {event.name}: {event.error}")
        elif isinstance(event, ResearchCompleted):
            self._console.print(
                f"  [green]Research structured:[/green] "
                f"{event.source_count} sources, {event.claim_count} claims"
            )
        elif isinstance(event, StageStarted):
            if event.technique_id:
                self._console.print(f"  [cyan]▸[/cyan] {event.stage}: {event.technique_id}")
            else:
                self._console.print(f"  [cyan]▸[/cyan] {event.stage}")
        elif isinstance(event, StageCompleted):
            dur = f" ({event.duration_secs:.1f}s)" if event.duration_secs else ""
            self._console.print(f"  [green]✓[/green] {event.stage}{dur}")
        elif isinstance(event, ArtifactWritten):
            self._console.print(f"  [dim]📄 {event.path}[/dim]")


def _short_error(exc: Exception, max_len: int = 80) -> str:
    """Format exception as 'TypeName: short message' for status display."""
    type_name = type(exc).__name__
    msg = str(exc).split("\n", 1)[0]
    if len(msg) > max_len:
        msg = msg[:max_len] + "..."
    return f"{type_name}: {msg}" if msg else type_name


async def run_analysis(config: AnalysisConfig, events: EventBus | None = None, rate_limiter: ProviderRateLimiter | None = None) -> Path:
    """Execute a full structured analysis pipeline.

    Args:
        config: Full analysis configuration.
        events: Optional event bus for progress visibility. If provided, events
            are emitted at key pipeline milestones. A RichProgressHandler is
            always subscribed so console output is visible. Pass your own
            EventBus to add additional subscribers.
        rate_limiter: Optional rate limiter for per-provider concurrency control.
            When provided (e.g. when multiple analyses run concurrently), LLM calls
            are throttled to avoid overwhelming the API key's rate limits.

    Returns:
        Path to the output directory containing all artifacts.
    """
    # Always create a real bus so RichProgressHandler output works.
    # If the caller passed one, use it; otherwise create a fresh one.
    bus = events if events is not None else EventBus()
    rich_handler = RichProgressHandler(console)
    bus.subscribe(rich_handler)

    run_id = uuid.uuid4().hex[:12]
    output_dir = config.output_dir / f"sat-{run_id}"

    console.print(
        Panel(
            f"[bold]{config.question}[/bold]",
            title="Structured Analytic Techniques",
            subtitle=f"Run {run_id}",
            box=box.ROUNDED,
        )
    )

    if config.evidence:
        console.print(f"📄 [dim]Evidence: {len(config.evidence)} characters[/dim]\n")
    elif not config.research.enabled:
        console.print(
            "[dim]Tip: Providing evidence with -e or -f (or enabling --research) often leads to better analysis.[/dim]\n"
        )

    provider = create_provider(config.provider, rate_limiter)
    writer = ArtifactWriter(output_dir, run_id, config.question, name=config.name)

    # Phase -1: Evidence Ingestion (file/URL parsing)
    if config.evidence_sources and config.ingestion.enabled:
        try:
            from sat.ingestion import ingest_evidence

            console.print("📥 [bold blue]Ingesting evidence sources...[/bold blue]")
            ingestion_result = await ingest_evidence(
                sources=config.evidence_sources,
                inline_evidence=config.evidence,
                config=config.ingestion,
            )
            writer.write_result(ingestion_result)
            for doc in ingestion_result.documents:
                status = f"  [green]✓[/green] {doc.source_name} ({doc.source_type})"
                if doc.parse_warnings:
                    status += f" [yellow]({', '.join(doc.parse_warnings)})[/yellow]"
                console.print(status)
            console.print(
                f"[dim]Combined: ~{ingestion_result.total_estimated_tokens} estimated tokens[/dim]"
            )
            config = config.model_copy(update={"evidence": ingestion_result.combined_markdown})
            for w in ingestion_result.warnings:
                console.print(f"[yellow]Warning: {w}[/yellow]")
        except Exception:
            logger.exception("Evidence ingestion failed")
            console.print("[yellow]Ingestion failed, using raw evidence[/yellow]")

    # Phase -0.5: Atomic Fact Decomposition (if enabled)
    if config.evidence and config.decomposition.enabled:
        try:
            from sat.decomposition import decompose_evidence

            console.print("🔬 [bold blue]Decomposing evidence into atomic facts...[/bold blue]")
            decomp_result = await decompose_evidence(
                evidence=config.evidence,
                provider=provider,
                config=config.decomposition,
            )
            writer.write_result(decomp_result)
            console.print(
                f"[green]Decomposition:[/green] {decomp_result.total_facts} facts from "
                f"{decomp_result.chunks_processed} chunk(s)"
            )
            if decomp_result.duplicates_removed > 0:
                console.print(
                    f"[dim]Deduplication removed {decomp_result.duplicates_removed} duplicate(s)[/dim]"
                )
            config = config.model_copy(update={"evidence": decomp_result.formatted_evidence})
            for w in decomp_result.warnings:
                console.print(f"[yellow]Warning: {w}[/yellow]")
        except Exception:
            logger.exception("Evidence decomposition failed")
            console.print("[yellow]Decomposition failed, using raw evidence[/yellow]")

    # Preprocessing: detect format, manage size, convert structured data
    if config.evidence and config.preprocessing.enabled:
        from sat.preprocessing import preprocess_evidence

        console.print("📋 Preprocessing evidence...")
        try:
            preproc_result = await preprocess_evidence(
                evidence=config.evidence,
                provider=provider,
                provider_name=config.provider.provider,
                config=config.preprocessing,
            )
            writer.write_result(preproc_result)
            config = config.model_copy(update={"evidence": preproc_result.formatted_evidence})
            if preproc_result.reduction_applied == "none":
                console.print(
                    f"[dim]Evidence: {preproc_result.original_format.value}, "
                    f"~{preproc_result.original_estimated_tokens} tokens (passthrough)[/dim]"
                )
            else:
                console.print(
                    f"[green]Evidence preprocessed:[/green] {preproc_result.original_format.value}, "
                    f"{preproc_result.original_estimated_tokens} → "
                    f"{preproc_result.output_estimated_tokens} est. tokens "
                    f"({preproc_result.reduction_applied})"
                )
            for w in preproc_result.warnings:
                console.print(f"[yellow]Warning: {w}[/yellow]")
        except Exception:
            logger.exception("Evidence preprocessing failed")
            console.print("[yellow]Preprocessing failed, using raw evidence[/yellow]")

    # Phase 0: Deep Research (if enabled)
    # Note: console.status() spinner is intentionally NOT used here — it suppresses
    # all console output from event handlers. Events provide real-time progress instead.
    # Research now runs even when evidence is provided; both sources are merged.
    if config.research.enabled:
        console.print("🔍 [bold blue]Running deep research...[/bold blue]")
        try:
            if config.research.mode == "multi":
                from sat.research.multi_runner import run_multi_research

                research_result = await run_multi_research(
                    question=config.question,
                    llm_provider=provider,
                    max_sources=config.research.max_sources,
                    events=bus,
                )
            else:
                from sat.research.registry import create_research_provider
                from sat.research.runner import run_research as run_deep_research

                research_prov = create_research_provider(
                    provider_name=config.research.provider,
                    api_key=config.research.api_key,
                    llm_provider=provider,
                )
                research_result = await run_deep_research(
                    question=config.question,
                    research_provider=research_prov,
                    llm_provider=provider,
                    max_sources=config.research.max_sources,
                    events=bus,
                )

            # Phase 0b: Source Verification (before writing research_result)
            if config.research.verification.enabled:
                try:
                    from sat.research.verification import verify_sources

                    verification_result = await verify_sources(
                        research_result=research_result,
                        provider_name=config.provider.provider,
                        verification_config=config.research.verification,
                    )
                    writer.write_result(verification_result)
                    # Annotate research_result claims with verification verdicts
                    verdict_map = {v.claim: v for v in verification_result.claim_verifications}
                    updated_claims = []
                    for claim in research_result.claims:
                        v = verdict_map.get(claim.claim)
                        if v:
                            claim = claim.model_copy(
                                update={
                                    "verified": True,
                                    "verification_verdict": v.verdict,
                                    "confidence": v.adjusted_confidence,
                                }
                            )
                        updated_claims.append(claim)
                    research_result = research_result.model_copy(
                        update={
                            "claims": updated_claims,
                            "verification_status": "verified",
                            "verification_summary": verification_result.verification_summary,
                        }
                    )
                    console.print(
                        f"[green]Verification:[/green] "
                        f"{verification_result.sources_fetched} sources verified, "
                        f"{sum(1 for v in verification_result.claim_verifications if v.verdict == 'SUPPORTED')} claims supported"
                    )
                except Exception:
                    logger.exception("Source verification failed")
                    console.print("[yellow]Verification failed, using unverified results[/yellow]")

            artifact = writer.write_result(research_result)
            await bus.emit(
                ArtifactWritten(
                    path=str(artifact.markdown_path),
                    technique_id=research_result.technique_id,
                    category="research",
                )
            )
            research_evidence = format_research_evidence(research_result)
            # Merge: if user evidence already exists, append research after it
            if config.evidence:
                merged_evidence = config.evidence + "\n\n" + research_evidence
            else:
                merged_evidence = research_evidence
            config = config.model_copy(update={"evidence": merged_evidence})
        except Exception:
            logger.exception("Deep research failed")
            console.print("[yellow]Research failed, continuing without evidence[/yellow]")

    # Phase 1: Select techniques
    if config.techniques:
        technique_ids = config.techniques
    else:
        with console.status("🔍 [bold blue]Auto-selecting techniques...", spinner="dots"):
            technique_ids = await select_techniques(config.question, config.evidence, provider)

    category_colors = {"diagnostic": "green", "contrarian": "yellow", "imaginative": "magenta"}
    plan_parts = []
    for tid in technique_ids:
        try:
            meta = get_technique(tid).metadata
            color = category_colors.get(meta.category, "white")
            plan_parts.append(f"[{color}]{meta.name}[/{color}]")
        except Exception:
            plan_parts.append(tid)
    console.print(f"📋 [bold]Analytic Plan:[/bold] {' → '.join(plan_parts)}\n")

    # Set up adversarial session if configured
    adversarial_session = None
    adversarial_exchanges = []
    if config.adversarial and config.adversarial.enabled:
        from sat.adversarial.pool import ProviderPool
        from sat.adversarial.session import AdversarialSession

        pool = ProviderPool(config.adversarial)
        adversarial_session = AdversarialSession(pool, config.adversarial)
        primary_ref = config.adversarial.providers.get("primary")
        challenger_ref = config.adversarial.providers.get("challenger")
        investigator_ref = config.adversarial.providers.get("investigator")
        adv_mode = config.adversarial.mode

        if adv_mode == "trident" and primary_ref and challenger_ref and investigator_ref:
            console.print(
                f"[bold cyan]Trident mode enabled ({config.adversarial.rounds} round(s))[/bold cyan]\n"
                f"  Primary:      [green]{primary_ref.provider}/{primary_ref.model}[/green]\n"
                f"  Challenger:   [yellow]{challenger_ref.provider}/{challenger_ref.model}[/yellow]\n"
                f"  Investigator: [magenta]{investigator_ref.provider}/{investigator_ref.model}[/magenta]"
            )
        elif primary_ref and challenger_ref:
            console.print(
                f"[bold cyan]Adversarial mode enabled ({config.adversarial.rounds} rounds)[/bold cyan]\n"
                f"  Primary:    [green]{primary_ref.provider}/{primary_ref.model}[/green]\n"
                f"  Challenger: [yellow]{challenger_ref.provider}/{challenger_ref.model}[/yellow]"
            )
        else:
            console.print(
                f"[bold cyan]Adversarial mode enabled ({config.adversarial.rounds} rounds)[/bold cyan]"
            )

    # Phase 2: Execute techniques in dependency layers
    # @decision DEC-PIPE-003: Layer-based parallel technique execution.
    # Techniques with satisfied dependencies run concurrently within a layer.
    # Adversarial critique runs per-technique immediately after completion.
    # Falls back to sequential if dependency resolution fails.
    prior_results: dict[str, ArtifactResult] = {}
    completed: list[str] = []

    from sat.techniques.registry import build_dependency_layers

    layers = build_dependency_layers(technique_ids)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        for layer in layers:

            async def _run_technique(tid: str) -> None:
                technique = get_technique(tid)
                meta = technique.metadata
                task = progress.add_task(f"Running {meta.name}...", total=None)

                try:
                    ctx = TechniqueContext(
                        question=config.question,
                        evidence=config.evidence,
                        prior_results=prior_results,
                    )
                    try:
                        result = await technique.execute(ctx, provider)
                    except Exception as first_exc:
                        if is_transient_error(first_exc):
                            logger.warning(
                                "Technique %s hit transient error (%s), retrying once...",
                                tid,
                                type(first_exc).__name__,
                            )
                            progress.update(task, description=f"[yellow]Retrying:[/yellow] {meta.name}")
                            result = await technique.execute(ctx, provider)
                        else:
                            raise
                    writer.write_result(result)
                    prior_results[tid] = result
                    completed.append(tid)
                    progress.update(task, description=f"✅ [green]Done:[/green] {meta.name}")

                    # Run adversarial analysis on this technique's output
                    if adversarial_session:
                        progress.update(
                            task,
                            description=f"[cyan]Critiquing:[/cyan] {meta.name}",
                        )
                        await bus.emit(StageStarted(stage="critique", technique_id=tid))
                        try:
                            exchange = await adversarial_session.run_adversarial_technique(
                                technique_result=result,
                                question=config.question,
                                evidence=config.evidence,
                            )
                            adversarial_exchanges.append(exchange)
                            for rnd in exchange.rounds:
                                writer.write_result(rnd.critique)
                                if rnd.rebuttal:
                                    writer.write_result(rnd.rebuttal)
                            if exchange.adjudication:
                                writer.write_result(exchange.adjudication)
                            if exchange.investigator_result:
                                writer.write_result(exchange.investigator_result)
                            if exchange.convergence:
                                writer.write_result(exchange.convergence)

                            last_rebuttal = exchange.rounds[-1].rebuttal if exchange.rounds else None
                            if last_rebuttal and last_rebuttal.revised_conclusions:
                                revised_summary = (
                                    f"{result.summary}\n\n"
                                    f"[Revised after adversarial critique]\n"
                                    f"{last_rebuttal.revised_conclusions}"
                                )
                                prior_results[tid] = result.model_copy(
                                    update={"summary": revised_summary}
                                )
                                revised_artifact = ArtifactResult(
                                    technique_id=f"{tid}-revised",
                                    technique_name=f"{meta.name} (Revised)",
                                    summary=revised_summary,
                                )
                                writer.write_result(revised_artifact)

                            if exchange.adjudication:
                                prior_results[f"{tid}-adjudication"] = exchange.adjudication
                            if exchange.investigator_result:
                                prior_results[f"{tid}-investigator"] = exchange.investigator_result
                            if exchange.convergence:
                                prior_results[f"{tid}-convergence"] = exchange.convergence

                            await bus.emit(StageCompleted(stage="critique", technique_id=tid))
                            progress.update(
                                task,
                                description=f"[green]Done + Critiqued:[/green] {meta.name}",
                            )
                        except Exception as exc:
                            logger.exception("Adversarial analysis failed for %s", tid)
                            progress.update(
                                task,
                                description=f"[yellow]Done (critique failed):[/yellow] {meta.name} ({_short_error(exc)})",
                            )
                except (ValidationError, TimeoutError, OSError) as exc:
                    logger.exception("Technique %s failed", tid)
                    progress.update(
                        task, description=f"[red]Failed:[/red] {meta.name} ({_short_error(exc)})"
                    )

                progress.stop_task(task)

            if len(layer) == 1:
                await _run_technique(layer[0])
            else:
                await asyncio.gather(*[_run_technique(tid) for tid in layer])

    # Phase 3: Synthesis
    synthesis_result = None
    if len(completed) >= 2:
        console.print("🏆 [bold cyan]Generating synthesis report...[/bold cyan]")
        try:
            synthesis_ctx = TechniqueContext(
                question=config.question,
                evidence=config.evidence,
                prior_results=prior_results,
            )
            synthesis_result = await run_synthesis(synthesis_ctx, provider)
            artifact = writer.write_result(synthesis_result)
            synthesis_path = artifact.json_path
        except Exception:
            logger.exception("Synthesis failed")
            synthesis_path = None
    else:
        synthesis_path = None
        if len(completed) < 2:
            console.print("[yellow]Skipping synthesis (fewer than 2 techniques completed)[/yellow]")

    # Phase 4: Write manifest
    adversarial_enabled = bool(config.adversarial and config.adversarial.enabled)
    providers_used = []
    if adversarial_enabled and config.adversarial and config.adversarial.providers:
        providers_used = list(config.adversarial.providers.keys())

    try:
        writer.write_manifest(
            techniques_selected=technique_ids,
            techniques_completed=completed,
            evidence_provided=config.evidence is not None,
            synthesis_path=synthesis_path,
            adversarial_enabled=adversarial_enabled,
            providers_used=providers_used,
        )
    except Exception:
        logger.exception("Manifest write failed — run artifacts exist but are not indexed")
        raise

    # Phase 5: Generate executive report
    if config.report.enabled:
        try:
            from sat.report import generate_report

            report_paths = generate_report(output_dir, fmt=config.report.fmt)
            for rp in report_paths:
                console.print(f"[green]Report:[/green] {rp}")
        except Exception:
            logger.exception("Report generation failed")
            raise

    # Print final answer
    console.print()
    if synthesis_result is not None:
        console.print(
            Panel(
                f"[bold]{synthesis_result.bottom_line_assessment}[/bold]",
                title="[green]Bottom Line[/green]",
                padding=(1, 2),
                box=box.ROUNDED,
            )
        )
    elif completed and prior_results:
        last_result = prior_results[completed[-1]]
        console.print(
            Panel(
                f"[bold]{last_result.summary}[/bold]",
                title="[green]Summary[/green]",
                padding=(1, 2),
                box=box.ROUNDED,
            )
        )

    # List artifacts — use actual paths from the writer rather than
    # reconstructing them from technique IDs. The writer's counter includes
    # preprocessing, research, and adversarial artifacts so a naive
    # 1-indexed position from `completed` would point to the wrong file.
    artifact_lines = []
    for artifact in writer.get_technique_artifacts():
        artifact_lines.append(f"  📄 {artifact.markdown_path}")
    if synthesis_path:
        artifact_lines.append(f"  📄 {synthesis_path}")

    console.print(
        Panel(
            f"Techniques: {len(completed)}/{len(technique_ids)} completed\n"
            f"Output: {output_dir}\n\n" + "\n".join(artifact_lines),
            title="[green]Artifacts[/green]",
            box=box.ROUNDED,
        )
    )

    return output_dir
