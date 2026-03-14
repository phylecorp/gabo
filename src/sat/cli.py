"""CLI entry point for the Structured Analytic Techniques tool.

@decision DEC-CLI-001: Typer for CLI with type-hint-based argument parsing.
Typer provides auto-completion, help generation, and rich output integration.
Two commands: `analyze` (main entry point) and `list-techniques` (discovery).
The CLI is a thin translation layer: it builds AnalysisConfig and delegates
to the pipeline.

@decision DEC-CLI-002: Trident mode flags with auto-detection fallback.
@title --adversarial-mode, --investigator-provider, --investigator-model flags
@status accepted
@rationale Users can explicitly request trident mode or let the CLI auto-detect
it when all three providers have API keys. Auto-detection: if investigator is not
explicitly disabled and a third provider is available, trident mode activates
automatically when adversarial is enabled. Explicit --adversarial-mode=dual
disables this.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path
from typing import Annotated, Optional

import typer
from dotenv import load_dotenv
from rich import box
from rich.console import Console
from rich.table import Table

from sat.config import AnalysisConfig, ProviderConfig

app = typer.Typer(
    name="sat",
    help="Gabo — structured analysis for any question.",
    no_args_is_help=True,
)
console = Console()


@app.command()
def analyze(
    question: Annotated[str, typer.Argument(help="The analytic question to investigate")],
    evidence: Annotated[
        Optional[str], typer.Option("--evidence", "-e", help="Evidence text to analyze")
    ] = None,
    evidence_file: Annotated[
        Optional[Path],
        typer.Option("--evidence-file", "-f", help="File or directory containing evidence"),
    ] = None,
    techniques: Annotated[
        Optional[str],
        typer.Option(
            "--techniques", "-t", help="Comma-separated technique IDs (auto-select if omitted)"
        ),
    ] = None,
    output_dir: Annotated[Path, typer.Option("--output-dir", "-o", help="Output directory")] = Path(
        "."
    ),
    provider: Annotated[str, typer.Option("--provider", "-p", help="LLM provider")] = "anthropic",
    model: Annotated[
        Optional[str],
        typer.Option(
            "--model", "-m", help="Model identifier (default: from env or provider default)"
        ),
    ] = None,
    api_key: Annotated[
        Optional[str], typer.Option("--api-key", help="API key (or set env var)")
    ] = None,
    research: Annotated[
        bool, typer.Option("--research/--no-research", "-r", help="Enable deep research")
    ] = False,
    research_provider: Annotated[
        Optional[str],
        typer.Option("--research-provider", help="Research provider: perplexity, brave, llm, auto"),
    ] = None,
    research_api_key: Annotated[
        Optional[str], typer.Option("--research-api-key", help="API key for research provider")
    ] = None,
    research_mode: Annotated[
        str,
        typer.Option("--research-mode", help="Research mode: 'single' or 'multi'"),
    ] = "multi",
    preprocess: Annotated[
        bool, typer.Option("--preprocess/--no-preprocess", help="Enable evidence preprocessing")
    ] = True,
    evidence_budget: Annotated[
        Optional[float],
        typer.Option("--evidence-budget", help="Fraction of context window for evidence (0.0-1.0)"),
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v", help="Verbose output")] = False,
    adversarial: Annotated[
        bool,
        typer.Option(
            "--adversarial/--no-adversarial", help="Enable adversarial multi-model critique"
        ),
    ] = True,
    challenger_provider: Annotated[
        Optional[str], typer.Option("--challenger-provider", help="Challenger LLM provider")
    ] = None,
    challenger_model: Annotated[
        Optional[str], typer.Option("--challenger-model", help="Challenger model identifier")
    ] = None,
    rounds: Annotated[int, typer.Option("--rounds", help="Number of critique-rebuttal rounds")] = 2,
    adversarial_mode: Annotated[
        Optional[str],
        typer.Option(
            "--adversarial-mode",
            help="Adversarial mode: 'dual' (default) or 'trident' (3-provider IPA)",
        ),
    ] = None,
    investigator_provider: Annotated[
        Optional[str],
        typer.Option(
            "--investigator-provider",
            help="Investigator LLM provider for trident mode (auto-detected if omitted)",
        ),
    ] = None,
    investigator_model: Annotated[
        Optional[str],
        typer.Option("--investigator-model", help="Investigator model identifier"),
    ] = None,
    config_file: Annotated[
        Optional[Path],
        typer.Option("--config", "-c", help="TOML config file for multi-model setup"),
    ] = None,
    report: Annotated[
        bool,
        typer.Option("--report/--no-report", help="Generate executive report"),
    ] = True,
    report_format: Annotated[
        str,
        typer.Option("--report-format", help="Report format: markdown, html, both"),
    ] = "both",
    verify: Annotated[
        bool,
        typer.Option("--verify/--no-verify", help="Verify cited sources against claims"),
    ] = True,
    verify_model: Annotated[
        Optional[str],
        typer.Option(
            "--verify-model", help="Model for source verification (default: cheap fast model)"
        ),
    ] = None,
    sources: Annotated[
        Optional[list[str]],
        typer.Option("--source", "-s", help="File path or URL to ingest as evidence (repeatable)"),
    ] = None,
    decompose: Annotated[
        bool,
        typer.Option("--decompose/--no-decompose", help="Decompose evidence into atomic facts"),
    ] = False,
) -> None:
    """Analyze a question using structured analytic techniques."""
    load_dotenv()
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolve evidence
    evidence_text = evidence
    if evidence_file:
        if not evidence_file.exists():
            console.print(f"[red]Error: Evidence path not found: {evidence_file}[/red]")
            raise typer.Exit(code=1)

        if evidence_file.is_dir():
            # Aggregate all files in directory
            parts = []
            # Sort files for deterministic output
            for p in sorted(evidence_file.rglob("*")):
                if p.is_file() and not p.name.startswith("."):
                    try:
                        content_text = p.read_text(encoding="utf-8")
                        rel_path = p.relative_to(evidence_file)
                        parts.append(f"--- Source: {rel_path} ---\n{content_text}")
                    except Exception as e:
                        if verbose:
                            console.print(f"[yellow]Warning: Could not read {p}: {e}[/yellow]")
            evidence_text = "\n\n".join(parts)
        else:
            evidence_text = evidence_file.read_text(encoding="utf-8")
    elif evidence is None and not sys.stdin.isatty():
        evidence_text = sys.stdin.read()

    # Parse technique IDs
    technique_ids = None
    if techniques:
        technique_ids = [t.strip() for t in techniques.split(",")]
        # Validate technique IDs
        import sat.techniques  # noqa: F401 — ensure registration
        from sat.techniques.registry import list_technique_ids

        valid = set(list_technique_ids())
        invalid = [t for t in technique_ids if t not in valid]
        if invalid:
            console.print(f"[red]Error: Unknown technique(s): {', '.join(invalid)}[/red]")
            console.print(f"Valid techniques: {', '.join(sorted(valid))}")
            raise typer.Exit(code=1)

    from sat.config import ResearchConfig, VerificationConfig

    verification_config = VerificationConfig(enabled=verify, model=verify_model)
    research_config = ResearchConfig(
        enabled=research,
        mode=research_mode,
        provider=research_provider or "auto",
        api_key=research_api_key,
        verification=verification_config,
    )

    # Build adversarial config if requested
    adv_config = None
    if adversarial or config_file:
        from sat.adversarial.config import AdversarialConfig, ProviderRef, RoleAssignment

        if config_file:
            # Load from TOML config file
            import tomllib

            if not config_file.exists():
                console.print(f"[red]Error: Config file not found: {config_file}[/red]")
                raise typer.Exit(code=1)
            with open(config_file, "rb") as f:
                toml_data = tomllib.load(f)
            adv_data = toml_data.get("adversarial", {})
            adv_config = AdversarialConfig(**adv_data)
        elif challenger_provider:
            # Cross-model: explicit challenger provider, resolve model from defaults if not given
            challenger_resolved_model = challenger_model
            if not challenger_resolved_model:
                challenger_resolved_model = ProviderConfig(
                    provider=challenger_provider
                ).resolve_model()

            # Determine mode and investigator
            resolved_adv_mode = adversarial_mode or "dual"
            inv_provider_name = investigator_provider
            inv_model_name = investigator_model

            providers_dict: dict = {
                "primary": ProviderRef(
                    provider=provider,
                    model=model or ProviderConfig(provider=provider).resolve_model(),
                    api_key=api_key,
                ),
                "challenger": ProviderRef(
                    provider=challenger_provider, model=challenger_resolved_model
                ),
            }
            role_kwargs: dict = {"primary": "primary", "challenger": "challenger"}

            # Auto-detect trident if no explicit mode given
            if adversarial_mode is None and inv_provider_name is None:
                from sat.config import resolve_investigator_provider

                inv_info = resolve_investigator_provider(provider, challenger_provider)
                if inv_info:
                    inv_provider_name, inv_model_name = inv_info
                    resolved_adv_mode = "trident"

            if resolved_adv_mode == "trident" or inv_provider_name:
                if inv_provider_name:
                    if not inv_model_name:
                        inv_model_name = ProviderConfig(provider=inv_provider_name).resolve_model()
                    providers_dict["investigator"] = ProviderRef(
                        provider=inv_provider_name, model=inv_model_name
                    )
                    role_kwargs["investigator"] = "investigator"
                    resolved_adv_mode = "trident"

            adv_config = AdversarialConfig(
                enabled=True,
                rounds=rounds,
                providers=providers_dict,
                roles=RoleAssignment(**role_kwargs),
                mode=resolved_adv_mode,
            )
        else:
            # Default adversarial: prefer a different provider as challenger
            from sat.config import resolve_challenger_provider

            resolved_model = model or ProviderConfig(provider=provider).resolve_model()
            challenger_info = resolve_challenger_provider(provider)
            if challenger_info:
                chall_provider, chall_model = challenger_info
            else:
                # No other provider available — self-critique fallback
                chall_provider, chall_model = provider, resolved_model

            # Determine mode and investigator
            resolved_adv_mode = adversarial_mode or "dual"
            inv_provider_name = investigator_provider
            inv_model_name = investigator_model

            # Auto-detect trident if no explicit mode and no explicit investigator override
            if adversarial_mode is None and inv_provider_name is None:
                from sat.config import resolve_investigator_provider

                inv_info = resolve_investigator_provider(provider, chall_provider)
                if inv_info:
                    inv_provider_name, inv_model_name = inv_info
                    resolved_adv_mode = "trident"

            providers_dict = {
                "primary": ProviderRef(provider=provider, model=resolved_model, api_key=api_key),
                "challenger": ProviderRef(provider=chall_provider, model=chall_model),
            }
            role_kwargs = {"primary": "primary", "challenger": "challenger"}

            if resolved_adv_mode == "trident" or inv_provider_name:
                if inv_provider_name:
                    if not inv_model_name:
                        inv_model_name = ProviderConfig(provider=inv_provider_name).resolve_model()
                    providers_dict["investigator"] = ProviderRef(
                        provider=inv_provider_name, model=inv_model_name
                    )
                    role_kwargs["investigator"] = "investigator"
                    resolved_adv_mode = "trident"

            adv_config = AdversarialConfig(
                enabled=True,
                rounds=rounds,
                providers=providers_dict,
                roles=RoleAssignment(**role_kwargs),
                mode=resolved_adv_mode,
            )

    from sat.config import DecompositionConfig, IngestionConfig, PreprocessingConfig

    preproc_config = PreprocessingConfig(enabled=preprocess)
    if evidence_budget is not None:
        preproc_config = preproc_config.model_copy(update={"budget_fraction": evidence_budget})

    from sat.config import ReportConfig

    report_config = ReportConfig(enabled=report, fmt=report_format)

    config = AnalysisConfig(
        question=question,
        evidence=evidence_text,
        techniques=technique_ids,
        output_dir=output_dir,
        provider=ProviderConfig(
            provider=provider,
            model=model,
            api_key=api_key,
        ),
        research=research_config,
        preprocessing=preproc_config,
        verbose=verbose,
        adversarial=adv_config,
        report=report_config,
        evidence_sources=sources,
        ingestion=IngestionConfig(),
        decomposition=DecompositionConfig(enabled=decompose),
    )

    from sat.pipeline import run_analysis

    asyncio.run(run_analysis(config))


@app.command("list-techniques")
def list_techniques(
    category: Annotated[
        Optional[str],
        typer.Option(
            "--category", "-c", help="Filter by category: diagnostic, contrarian, imaginative"
        ),
    ] = None,
) -> None:
    """List all available structured analytic techniques."""
    import sat.techniques  # noqa: F401 — ensure registration
    from sat.techniques.registry import get_all_techniques, get_techniques_by_category

    if category:
        techniques = get_techniques_by_category(category)
        if not techniques:
            console.print(f"[red]Unknown category: {category}[/red]")
            console.print("Valid categories: diagnostic, contrarian, imaginative")
            raise typer.Exit(code=1)
    else:
        techniques = get_all_techniques()

    table = Table(title="Structured Analytic Techniques", box=box.ROUNDED)
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="bold")
    table.add_column("Category")
    table.add_column("Description")

    category_colors = {
        "diagnostic": "green",
        "contrarian": "yellow",
        "imaginative": "magenta",
    }

    for t in techniques:
        m = t.metadata
        color = category_colors.get(m.category, "white")
        table.add_row(m.id, m.name, f"[{color}]{m.category}[/{color}]", m.description)

    console.print(table)


@app.command("report")
def report_cmd(
    output_dir: Annotated[
        Path, typer.Argument(help="SAT output directory containing manifest.json")
    ],
    fmt: Annotated[
        str,
        typer.Option("--format", "-f", help="Report format: markdown, html, both"),
    ] = "both",
) -> None:
    """Regenerate executive report from existing analysis output."""
    if not output_dir.exists():
        console.print(f"[red]Error: Directory not found: {output_dir}[/red]")
        raise typer.Exit(code=1)

    manifest = output_dir / "manifest.json"
    if not manifest.exists():
        console.print(f"[red]Error: No manifest.json in {output_dir}[/red]")
        raise typer.Exit(code=1)

    from sat.report import generate_report

    try:
        paths = generate_report(output_dir, fmt=fmt)
        for p in paths:
            console.print(f"[green]Generated:[/green] {p}")
    except Exception as e:
        console.print(f"[red]Report generation failed: {e}[/red]")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
