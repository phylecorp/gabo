"""Test that all prompt modules produce valid prompt tuples.

@decision DEC-TEST-PROMPTS-001: Prompt interface contract verification.
Tests that every registered technique's build_prompt returns a valid
(system_prompt, messages) tuple with the question in the user message,
evidence included when provided, and graceful handling when no evidence.
"""

from __future__ import annotations

import sat.techniques  # noqa: F401

from sat.techniques.base import TechniqueContext
from sat.techniques.registry import get_all_techniques


class TestPrompts:
    """All techniques should produce valid prompts from their build_prompt method."""

    def test_all_techniques_build_prompts(self):
        """Every registered technique should return (str, list[LLMMessage])."""
        ctx = TechniqueContext(
            question="Will Country X pursue nuclear weapons in the next 5 years?",
            evidence="Recent satellite imagery shows new construction at known nuclear facilities.",
        )
        for technique in get_all_techniques():
            system_prompt, messages = technique.build_prompt(ctx)
            assert isinstance(system_prompt, str)
            assert len(system_prompt) > 100, f"{technique.metadata.id} system prompt too short"
            assert isinstance(messages, list)
            assert len(messages) >= 1
            assert messages[0].role == "user"
            assert ctx.question in messages[0].content

    def test_prompts_include_evidence_when_provided(self):
        """Evidence should appear in user messages when provided."""
        evidence = "Top-secret intelligence report: Subject purchased centrifuge components."
        ctx = TechniqueContext(
            question="Test question?",
            evidence=evidence,
        )
        for technique in get_all_techniques():
            _, messages = technique.build_prompt(ctx)
            assert evidence in messages[0].content, (
                f"{technique.metadata.id} doesn't include evidence in prompt"
            )

    def test_prompts_work_without_evidence(self):
        """Prompts should work even without evidence."""
        ctx = TechniqueContext(question="Simple question?")
        for technique in get_all_techniques():
            system_prompt, messages = technique.build_prompt(ctx)
            assert isinstance(system_prompt, str)
            assert len(messages) >= 1
