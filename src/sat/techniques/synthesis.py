"""Synthesis technique: integrates findings from all prior techniques.

This is not registered in the technique registry — it runs as a special
final step in the pipeline, not as a selectable technique.
"""

from __future__ import annotations

from sat.models.synthesis import SynthesisResult
from sat.prompts.synthesis import build_prompt
from sat.providers.base import LLMProvider
from sat.techniques.base import TechniqueContext


async def run_synthesis(
    ctx: TechniqueContext,
    provider: LLMProvider,
) -> SynthesisResult:
    """Generate a synthesis report from all prior technique results.

    Args:
        ctx: Technique context — prior_results should contain ALL technique outputs.
        provider: LLM provider for generating the synthesis.

    Returns:
        SynthesisResult with integrated findings and bottom-line assessment.
    """
    system_prompt, messages = build_prompt(ctx)
    result = await provider.generate_structured(
        system_prompt=system_prompt,
        messages=messages,
        output_schema=SynthesisResult,
        max_tokens=16384,
    )
    assert isinstance(result, SynthesisResult)
    # Enforce canonical identity: the LLM may produce an arbitrary technique_id
    # (e.g. "SYNTH-001"). Override with the well-known "synthesis" ID so that
    # ArtifactWriter produces a predictable filename and the manifest path is
    # deterministic. Mirrors the pattern used in Technique.execute().
    result = result.model_copy(
        update={
            "technique_id": "synthesis",
            "technique_name": "Synthesis Report",
        }
    )
    return result
