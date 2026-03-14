"""SAT MCP Server — expose Structured Analytic Techniques via Model Context Protocol.

Allows any MCP-capable LLM to drive the full SAT analysis pipeline step by step:
list techniques, create a session, iterate through technique prompts, submit results,
run adversarial critique, and produce a final synthesis with artifact output.

@decision DEC-MCP-SERVER-001
@title FastMCP server with session-based multi-step analysis tools
@status accepted
@rationale MCP tools are individually stateless, but analysis requires accumulated
state across techniques. The server uses in-memory sessions (DEC-MCP-SESSION-001)
to bridge this gap. Each tool returns structured dicts that MCP serializes as JSON.
The connecting LLM executes prompts and returns results — SAT handles validation,
post-processing, adversarial critique, and artifact writing. This keeps the analysis
framework LLM-agnostic while the connecting model provides the reasoning.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from mcp.server.fastmcp import FastMCP
from pydantic import ValidationError

# Ensure all 12 techniques are registered before any tool calls
import sat.techniques  # noqa: F401

from sat.adversarial.config import AdversarialConfig, ProviderRef, RoleAssignment
from sat.adversarial.pool import ProviderPool
from sat.adversarial.session import AdversarialSession
from sat.artifacts import ArtifactWriter
from sat.config import PROVIDER_API_KEY_ENVS, ProviderConfig
from sat.mcp_session import AnalysisSession, create_session, get_session
from sat.models.adversarial import AdversarialExchange
from sat.models.base import ArtifactResult
from sat.models.synthesis import SynthesisResult
from sat.prompts.synthesis import build_prompt as build_synthesis_prompt
from sat.providers.registry import create_provider
from sat.research.multi_runner import run_multi_research
from sat.techniques.base import TechniqueContext
from sat.techniques.registry import get_all_techniques, get_metadata, get_technique

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "sat-analysis",
    instructions=(
        "Structured Analytic Techniques (SAT) server. Provides CIA Tradecraft Primer "
        "analysis techniques. Workflow: sat_ingest (optional, for files/URLs) -> "
        "sat_list_techniques -> sat_new_session -> "
        "loop(sat_next_prompt -> execute prompt -> sat_submit_result) -> "
        "sat_get_synthesis_prompt -> execute prompt -> sat_submit_synthesis."
    ),
)


@mcp.tool()
async def sat_list_techniques() -> list[dict]:
    """List all available structured analytic techniques.

    Returns metadata for all 12 CIA Tradecraft Primer techniques including
    id, name, category (diagnostic/contrarian/imaginative), description,
    and execution order. Use this to understand what techniques are available
    before creating an analysis session.
    """
    metadata = get_metadata()
    return [
        {
            "id": m.id,
            "name": m.name,
            "category": m.category,
            "description": m.description,
            "order": m.order,
        }
        for m in metadata
    ]


@mcp.tool()
async def sat_new_session(
    question: str,
    evidence: str | None = None,
    techniques: list[str] | None = None,
) -> dict:
    """Create a new analysis session for the given question.

    Args:
        question: The analytic question to investigate. Be specific and focused.
        evidence: Optional background evidence, intelligence, or context to inform
            the analysis. If not provided, you can use sat_research first.
        techniques: Optional list of technique IDs to apply, in order. If not
            provided, all techniques are included sorted by category order
            (diagnostic -> contrarian -> imaginative). You can pick a subset
            based on the question's needs.

    Returns:
        Dict with session_id, technique list, and count of techniques to execute.
    """
    if techniques:
        # Validate all technique IDs
        for tid in techniques:
            get_technique(tid)  # Raises ValueError if unknown
        technique_ids = techniques
    else:
        technique_ids = [t.metadata.id for t in get_all_techniques()]

    session = create_session(
        question=question,
        evidence=evidence,
        technique_ids=technique_ids,
    )

    return {
        "session_id": session.session_id,
        "question": question,
        "techniques": technique_ids,
        "total_techniques": len(technique_ids),
        "status": "created",
    }


@mcp.tool()
async def sat_next_prompt(session_id: str) -> dict:
    """Get the next technique's prompt to execute.

    Returns the system prompt, user messages, and JSON output schema for the
    next technique in the session. Execute this prompt with your LLM capabilities
    and submit the JSON result via sat_submit_result.

    Args:
        session_id: The session ID from sat_new_session.

    Returns:
        Dict with technique_id, system_prompt, messages, output_json_schema,
        and progress info. If all techniques are done, returns status "complete".
    """
    session = get_session(session_id)

    if session.current_index >= len(session.technique_ids):
        session.completed = True
        return {
            "status": "all_techniques_complete",
            "message": "All techniques done. Call sat_get_synthesis_prompt next.",
            "techniques_completed": list(session.prior_results.keys()),
        }

    technique_id = session.technique_ids[session.current_index]
    technique = get_technique(technique_id)

    ctx = TechniqueContext(
        question=session.question,
        evidence=session.evidence,
        prior_results=session.prior_results,
    )

    system_prompt, messages = technique.build_prompt(ctx)
    schema = technique.output_schema.model_json_schema()

    return {
        "status": "ready",
        "technique_id": technique_id,
        "technique_name": technique.metadata.name,
        "technique_category": technique.metadata.category,
        "progress": f"{session.current_index + 1}/{len(session.technique_ids)}",
        "system_prompt": system_prompt,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "output_json_schema": schema,
    }


@mcp.tool()
async def sat_submit_result(session_id: str, result_json: str) -> dict:
    """Submit the LLM's JSON result for the current technique.

    Validates the JSON against the technique's schema, runs post-processing
    (e.g. ACH inconsistency scoring), optionally runs adversarial critique,
    stores the result, and advances to the next technique.

    Args:
        session_id: The session ID from sat_new_session.
        result_json: The JSON string output from executing the technique prompt.
            Must conform to the output_json_schema from sat_next_prompt.

    Returns:
        Dict with validation status, post-processing info, adversarial critique
        summary (if enabled), and next technique info.
    """
    session = get_session(session_id)

    if session.current_index >= len(session.technique_ids):
        return {"error": "All techniques already completed"}

    technique_id = session.technique_ids[session.current_index]
    technique = get_technique(technique_id)

    # Parse and validate JSON against technique schema
    try:
        raw = json.loads(result_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON: {exc}"}

    try:
        result = technique.output_schema.model_validate(raw)
    except ValidationError as exc:
        return {
            "error": "Schema validation failed",
            "details": exc.errors(),
            "expected_schema": technique.output_schema.model_json_schema(),
        }

    # Run post-processing (e.g. ACH scoring)
    result = technique.post_process(result)

    # Optionally run adversarial critique
    critique_summary = None
    adversarial_enabled = _is_adversarial_enabled()
    if adversarial_enabled:
        try:
            exchange = await _run_adversarial(session, result)
            session.adversarial_exchanges.append(exchange)
            critique_summary = _summarize_exchange(exchange)
        except Exception as exc:
            logger.warning("Adversarial critique failed for %s: %s", technique_id, exc)
            critique_summary = {"error": f"Adversarial critique failed: {exc}"}

    # Store result and advance
    session.prior_results[technique_id] = result
    session.current_index += 1

    has_more = session.current_index < len(session.technique_ids)
    next_technique = None
    if has_more:
        next_technique = session.technique_ids[session.current_index]

    response: dict = {
        "status": "accepted",
        "technique_id": technique_id,
        "post_processed": True,
        "has_more_techniques": has_more,
    }
    if next_technique:
        response["next_technique_id"] = next_technique
    if critique_summary:
        response["adversarial_critique"] = critique_summary

    return response


@mcp.tool()
async def sat_get_synthesis_prompt(session_id: str) -> dict:
    """Get the synthesis prompt after all techniques are complete.

    The synthesis integrates findings from all techniques into a coherent
    assessment with convergent judgments, divergent signals, and a bottom-line
    assessment.

    Args:
        session_id: The session ID from sat_new_session.

    Returns:
        Dict with system_prompt, messages, and output_json_schema for the
        synthesis. Execute this prompt and submit via sat_submit_synthesis.
    """
    session = get_session(session_id)

    if session.current_index < len(session.technique_ids):
        remaining = session.technique_ids[session.current_index :]
        return {
            "error": "Not all techniques completed yet",
            "remaining_techniques": remaining,
            "completed": list(session.prior_results.keys()),
        }

    ctx = TechniqueContext(
        question=session.question,
        evidence=session.evidence,
        prior_results=session.prior_results,
    )

    system_prompt, messages = build_synthesis_prompt(ctx)
    schema = SynthesisResult.model_json_schema()

    return {
        "status": "ready",
        "system_prompt": system_prompt,
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "output_json_schema": schema,
        "techniques_completed": list(session.prior_results.keys()),
    }


@mcp.tool()
async def sat_submit_synthesis(session_id: str, result_json: str) -> dict:
    """Submit the synthesis result and write all artifacts to disk.

    Validates the synthesis JSON, writes all technique results, adversarial
    exchanges, and the synthesis as Markdown + JSON artifacts. Produces a
    manifest.json summarizing the full run.

    Args:
        session_id: The session ID from sat_new_session.
        result_json: The JSON string output from executing the synthesis prompt.
            Must conform to the output_json_schema from sat_get_synthesis_prompt.

    Returns:
        Dict with output directory path, artifact count, and manifest location.
    """
    session = get_session(session_id)

    # Parse and validate
    try:
        raw = json.loads(result_json)
    except json.JSONDecodeError as exc:
        return {"error": f"Invalid JSON: {exc}"}

    try:
        synthesis = SynthesisResult.model_validate(raw)
    except ValidationError as exc:
        return {
            "error": "Schema validation failed",
            "details": exc.errors(),
        }

    # Write artifacts
    output_dir = Path(os.environ.get("SAT_OUTPUT_DIR", ".")) / f"sat-{session.session_id}"
    writer = ArtifactWriter(output_dir, session.session_id, session.question)

    # Write technique results in order
    for tid in session.technique_ids:
        if tid in session.prior_results:
            writer.write_result(session.prior_results[tid])

    # Write adversarial exchanges
    for exchange in session.adversarial_exchanges:
        for debate_round in exchange.rounds:
            writer.write_result(debate_round.critique)
            if debate_round.rebuttal:
                writer.write_result(debate_round.rebuttal)
        if exchange.adjudication:
            writer.write_result(exchange.adjudication)

    # Write synthesis — capture the returned Artifact to get the actual path.
    # The synthesis filename includes the writer counter and canonical technique_id
    # (e.g. "07-synthesis.md") so we cannot hardcode it.
    synthesis_artifact = writer.write_result(synthesis)

    # Write manifest
    manifest_path = writer.write_manifest(
        techniques_selected=session.technique_ids,
        techniques_completed=list(session.prior_results.keys()),
        evidence_provided=session.evidence is not None,
        synthesis_path=str(synthesis_artifact.markdown_path),
        adversarial_enabled=len(session.adversarial_exchanges) > 0,
    )

    session.completed = True

    return {
        "status": "complete",
        "output_dir": str(output_dir),
        "manifest_path": str(manifest_path),
        "artifacts_written": len(session.prior_results) + 1,  # +1 for synthesis
        "adversarial_exchanges": len(session.adversarial_exchanges),
    }


@mcp.tool()
async def sat_research(question: str) -> dict:
    """Run deep research to gather evidence for an analytic question.

    Uses available research backends (OpenAI deep research, Perplexity,
    Gemini deep research, Brave search, or LLM fallback) to gather and
    structure evidence. Requires at least one research provider API key
    and an LLM provider for evidence structuring.

    Args:
        question: The analytic question to research. Be specific about what
            facts, context, and evidence would be useful for analysis.

    Returns:
        Dict with formatted evidence string suitable for passing to
        sat_new_session as the evidence parameter.
    """
    # Create LLM provider for structuring from env vars
    provider_name = os.environ.get("SAT_PRIMARY_PROVIDER", "anthropic")
    model = os.environ.get("SAT_PRIMARY_MODEL")
    api_key = os.environ.get("SAT_PRIMARY_API_KEY")

    provider_config = ProviderConfig(
        provider=provider_name,
        model=model,
        api_key=api_key,
    )
    llm_provider = create_provider(provider_config)

    research_result = await run_multi_research(
        question=question,
        llm_provider=llm_provider,
    )

    return {
        "status": "complete",
        "formatted_evidence": research_result.formatted_evidence,
        "sources_count": len(research_result.sources),
        "claims_count": len(research_result.claims),
        "research_provider": research_result.research_provider,
        "gaps_identified": research_result.gaps_identified,
    }


@mcp.tool()
async def sat_ingest(sources: list[str], inline_evidence: str | None = None) -> dict:
    """Ingest files and URLs into normalized evidence text.

    Parses PDFs, DOCX, PPTX, XLSX, HTML, images, and URLs into markdown.
    Use the returned formatted_evidence as the evidence parameter for sat_new_session.

    Args:
        sources: List of file paths or URLs to ingest.
        inline_evidence: Optional additional inline evidence text.

    Returns:
        Dict with formatted_evidence, sources_count, total_estimated_tokens,
        source_manifest, and warnings.
    """
    from sat.config import IngestionConfig
    from sat.ingestion import ingest_evidence

    result = await ingest_evidence(
        sources=sources,
        inline_evidence=inline_evidence,
        config=IngestionConfig(),
    )

    return {
        "status": "complete",
        "formatted_evidence": result.combined_markdown,
        "sources_count": len(result.documents),
        "total_estimated_tokens": result.total_estimated_tokens,
        "source_manifest": result.source_manifest,
        "warnings": result.warnings,
    }


# --- Internal helpers ---


def _is_adversarial_enabled() -> bool:
    """Check if adversarial critique is enabled via environment variables."""
    enabled = os.environ.get("SAT_ADVERSARIAL_ENABLED", "").lower()
    if enabled in ("true", "1", "yes"):
        return True
    # Also enable if challenger provider is explicitly configured
    if os.environ.get("SAT_CHALLENGER_PROVIDER"):
        return True
    return False


def _build_adversarial_config() -> AdversarialConfig:
    """Build adversarial config from environment variables."""
    challenger_provider = os.environ.get("SAT_CHALLENGER_PROVIDER", "anthropic")
    challenger_model = os.environ.get("SAT_CHALLENGER_MODEL")
    challenger_api_key = os.environ.get("SAT_CHALLENGER_API_KEY")

    # Resolve challenger API key from standard env vars if not explicitly set
    if not challenger_api_key:
        env_var = PROVIDER_API_KEY_ENVS.get(
            challenger_provider, f"{challenger_provider.upper()}_API_KEY"
        )
        challenger_api_key = os.environ.get(env_var)

    # Primary provider for rebuttals (defaults to challenger if not set)
    primary_provider = os.environ.get("SAT_PRIMARY_PROVIDER", challenger_provider)
    primary_model = os.environ.get("SAT_PRIMARY_MODEL", challenger_model)
    primary_api_key = os.environ.get("SAT_PRIMARY_API_KEY")

    if not primary_api_key:
        env_var = PROVIDER_API_KEY_ENVS.get(primary_provider, f"{primary_provider.upper()}_API_KEY")
        primary_api_key = os.environ.get(env_var)

    # Resolve models via ProviderConfig defaults
    if not challenger_model:
        challenger_model = ProviderConfig(provider=challenger_provider).resolve_model()
    if not primary_model:
        primary_model = ProviderConfig(provider=primary_provider).resolve_model()

    return AdversarialConfig(
        enabled=True,
        rounds=1,
        providers={
            "primary": ProviderRef(
                provider=primary_provider,
                model=primary_model,
                api_key=primary_api_key,
            ),
            "challenger": ProviderRef(
                provider=challenger_provider,
                model=challenger_model,
                api_key=challenger_api_key,
            ),
        },
        roles=RoleAssignment(
            primary="primary",
            challenger="challenger",
        ),
    )


async def _run_adversarial(session: AnalysisSession, result: ArtifactResult) -> AdversarialExchange:
    """Run adversarial critique on a technique result."""
    config = _build_adversarial_config()
    pool = ProviderPool(config)
    adv_session = AdversarialSession(pool, config)

    return await adv_session.run_adversarial_technique(
        technique_result=result,
        question=session.question,
        evidence=session.evidence,
    )


def _summarize_exchange(exchange: AdversarialExchange) -> dict:
    """Produce a brief summary of an adversarial exchange for the tool response."""
    summary: dict = {
        "technique_id": exchange.technique_id,
        "rounds": len(exchange.rounds),
    }

    if exchange.rounds:
        last_critique = exchange.rounds[-1].critique
        summary["critique_severity"] = last_critique.severity
        summary["challenges_count"] = len(last_critique.challenges)
        summary["revised_confidence"] = last_critique.revised_confidence

        last_rebuttal = exchange.rounds[-1].rebuttal
        if last_rebuttal:
            summary["accepted_challenges"] = len(last_rebuttal.accepted_challenges)
            summary["revised_conclusions_excerpt"] = (
                last_rebuttal.revised_conclusions[:200] if last_rebuttal.revised_conclusions else ""
            )

    if exchange.adjudication:
        summary["adjudication_summary"] = exchange.adjudication.synthesis_assessment[:200]

    return summary


def main() -> None:
    """Entry point for sat-mcp console script."""
    mcp.run()


if __name__ == "__main__":
    main()
