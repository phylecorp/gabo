"""Tests for decomposition prompts.

@decision DEC-DECOMP-002: LLM prompts for fact extraction and deduplication.
@title Tests for build_decomposition_prompt and build_dedup_prompt
@status accepted
@rationale Verifies prompt structure, date injection, and return types.
"""

from __future__ import annotations

from datetime import date

from sat.decomposition.prompts import build_decomposition_prompt, build_dedup_prompt
from sat.providers.base import LLMMessage


class TestBuildDecompositionPrompt:
    def test_returns_tuple_of_str_and_messages(self):
        system, messages = build_decomposition_prompt(
            evidence_chunk="Some evidence.",
            prior_facts=[],
            source_index="- [abc12345]: source.txt",
        )
        assert isinstance(system, str)
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert isinstance(messages[0], LLMMessage)
        assert messages[0].role == "user"

    def test_date_injection(self):
        today = date.today().isoformat()
        _, messages = build_decomposition_prompt(
            evidence_chunk="Evidence text.",
            prior_facts=[],
            source_index="- [abc12345]: doc.txt",
        )
        assert today in messages[0].content

    def test_prior_facts_included(self):
        prior = ["[F1] The sky is blue.", "[F2] Water is wet."]
        _, messages = build_decomposition_prompt(
            evidence_chunk="More evidence.",
            prior_facts=prior,
            source_index="- [abc12345]: doc.txt",
        )
        assert "F1" in messages[0].content
        assert "F2" in messages[0].content

    def test_evidence_in_user_message(self):
        _, messages = build_decomposition_prompt(
            evidence_chunk="Unique evidence phrase xyz.",
            prior_facts=[],
            source_index="- [abc12345]: doc.txt",
        )
        assert "Unique evidence phrase xyz." in messages[0].content

    def test_system_prompt_is_nonempty(self):
        system, _ = build_decomposition_prompt("ev", [], "index")
        assert len(system) > 50


class TestBuildDedupPrompt:
    def test_returns_tuple_of_str_and_messages(self):
        system, messages = build_dedup_prompt('{"facts": []}')
        assert isinstance(system, str)
        assert isinstance(messages, list)
        assert len(messages) == 1
        assert messages[0].role == "user"

    def test_facts_json_in_user_message(self):
        facts_json = '[{"fact_id": "F1", "claim": "X is true."}]'
        _, messages = build_dedup_prompt(facts_json)
        assert facts_json in messages[0].content

    def test_system_prompt_is_nonempty(self):
        system, _ = build_dedup_prompt("{}")
        assert len(system) > 50
