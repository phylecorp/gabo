"""Tests for Anthropic provider implementation.

@decision DEC-TEST-ANTHRO-001: Unit tests for _deserialize_tool_input covering recursive JSON-string handling.
@mock-exempt: Tests static method directly — no API calls or mocking needed.

Covers three layers of the JSON-string deserialization defense-in-depth strategy:
  Layer 1 — AnthropicProvider._deserialize_tool_input (recursive via _deep_deserialize)
  Layer 2 — ArtifactResult model_validator(mode='before') safety net
  Layer 3 — End-to-end: raw Anthropic-style double-encoded payload -> RebuttalResult
"""

from __future__ import annotations

import json


from sat.models.adversarial import RebuttalPoint, RebuttalResult
from sat.providers.anthropic import AnthropicProvider


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _deser(data: dict) -> dict:
    """Shorthand for AnthropicProvider._deserialize_tool_input."""
    return AnthropicProvider._deserialize_tool_input(data)


# ---------------------------------------------------------------------------
# Layer 1: _deserialize_tool_input / _deep_deserialize
# ---------------------------------------------------------------------------


def test_deserialize_flat_strings():
    """Top-level list and dict strings are parsed to native Python types."""
    data = {
        "items": '["a", "b", "c"]',
        "meta": '{"key": "value"}',
    }
    result = _deser(data)
    assert result["items"] == ["a", "b", "c"]
    assert result["meta"] == {"key": "value"}


def test_deserialize_nested_dict_with_string_values():
    """A dict nested inside another dict has string values that need parsing."""
    inner = {"scores": "[1, 2, 3]"}
    data = {"outer": inner}
    result = _deser(data)
    # The nested dict is walked; its 'scores' key should be parsed
    assert result["outer"]["scores"] == [1, 2, 3]


def test_deserialize_list_of_json_strings():
    """A list whose items are JSON-encoded strings are each parsed."""
    raw_list = ['{"a": 1}', '{"b": 2}']
    data = {"entries": json.dumps(raw_list)}
    result = _deser(data)
    # The outer string is parsed to a list, then each string item inside is parsed too
    assert result["entries"] == [{"a": 1}, {"b": 2}]


def test_deserialize_deeply_nested():
    """Three levels of nesting are all correctly unwrapped."""
    leaf = {"z": 99}
    level2 = {"leaf": json.dumps(leaf)}
    level1 = {"level2": json.dumps(level2)}
    data = {"level1": json.dumps(level1)}
    result = _deser(data)
    assert result["level1"]["level2"]["leaf"] == {"z": 99}


def test_deserialize_malformed_json_preserved():
    """Strings that look like JSON but are not valid are kept as-is."""
    data = {
        "bad_list": "[not, valid, json",
        "bad_dict": "{missing: quotes}",
    }
    result = _deser(data)
    assert result["bad_list"] == "[not, valid, json"
    assert result["bad_dict"] == "{missing: quotes}"


def test_deserialize_non_json_strings_untouched():
    """Regular strings that do not start with [ or { are left alone."""
    data = {
        "name": "hello world",
        "empty": "",
        "number_str": "42",
        "whitespace": "   ",
    }
    result = _deser(data)
    assert result == data


def test_deserialize_mixed_types():
    """Mix of ints, bools, strings, lists, and dicts all handled correctly."""
    data = {
        "count": 5,
        "flag": True,
        "label": "plain text",
        "tags": ["x", "y"],
        "nested_str": '{"a": 1}',
        "nested_dict": {"inner_str": '["p", "q"]'},
    }
    result = _deser(data)
    assert result["count"] == 5
    assert result["flag"] is True
    assert result["label"] == "plain text"
    assert result["tags"] == ["x", "y"]
    assert result["nested_str"] == {"a": 1}
    assert result["nested_dict"]["inner_str"] == ["p", "q"]


def test_deserialize_empty_structures():
    """Empty dict, empty list, and empty string are all handled without error."""
    data = {
        "empty_dict": "{}",
        "empty_list": "[]",
        "empty_string": "",
        "plain": {},
    }
    result = _deser(data)
    assert result["empty_dict"] == {}
    assert result["empty_list"] == []
    assert result["empty_string"] == ""
    assert result["plain"] == {}


# ---------------------------------------------------------------------------
# Layer 1 + schema: RebuttalResult end-to-end from double-encoded payload
# ---------------------------------------------------------------------------


def test_rebuttal_result_from_double_encoded_anthropic_response():
    """Simulate the exact real-world scenario that caused the bug.

    Anthropic returns a tool_use block where list fields are JSON-encoded
    strings instead of native lists.  After _deserialize_tool_input, the
    data must validate as a RebuttalResult without error.
    """
    rebuttal_points = [
        {
            "challenge": "Insufficient sample size",
            "response": "N=500 is adequate for this domain",
            "conceded": False,
        },
        {"challenge": "Selection bias", "response": "Random sampling was used", "conceded": True},
    ]
    # Simulate what Anthropic sends: list fields as JSON strings
    raw_tool_input = {
        "technique_id": "steel-man",
        "technique_name": "Steel Man",
        "summary": "Primary defended two challenges, conceding one.",
        "accepted_challenges": '["Selection bias noted and incorporated"]',
        "rejected_challenges": json.dumps(rebuttal_points),
        "revised_conclusions": "Conclusions stand with minor caveats.",
    }

    deserialized = AnthropicProvider._deserialize_tool_input(raw_tool_input)

    # accepted_challenges must be a list of strings
    assert isinstance(deserialized["accepted_challenges"], list)
    assert deserialized["accepted_challenges"] == ["Selection bias noted and incorporated"]

    # rejected_challenges must be a list of dicts (each matching RebuttalPoint)
    assert isinstance(deserialized["rejected_challenges"], list)
    assert len(deserialized["rejected_challenges"]) == 2

    # Full Pydantic validation must succeed
    result = RebuttalResult.model_validate(deserialized)
    assert isinstance(result, RebuttalResult)
    assert len(result.accepted_challenges) == 1
    assert len(result.rejected_challenges) == 2
    assert isinstance(result.rejected_challenges[0], RebuttalPoint)
    assert result.rejected_challenges[0].challenge == "Insufficient sample size"
    assert result.rejected_challenges[1].conceded is True


# ---------------------------------------------------------------------------
# Layer 2: ArtifactResult model_validator safety net
# ---------------------------------------------------------------------------


def test_artifact_result_model_validator_fallback():
    """The model_validator on ArtifactResult parses string fields independently of the provider.

    This verifies the Layer 2 safety net: even if _deserialize_tool_input is
    never called (e.g., a different provider path), Pydantic itself will unwrap
    JSON-encoded list/dict strings on ArtifactResult subclasses.
    """
    # Use RebuttalResult (subclass of ArtifactResult) to exercise inheritance
    raw = {
        "technique_id": "adv-rebuttal",
        "technique_name": "Adversarial Rebuttal",
        "summary": "Test summary.",
        # Pass accepted_challenges as a JSON string — bypassing provider deserialization
        "accepted_challenges": '["Point A", "Point B"]',
        "rejected_challenges": [],
        "revised_conclusions": "",
    }

    result = RebuttalResult.model_validate(raw)
    assert isinstance(result, RebuttalResult)
    assert result.accepted_challenges == ["Point A", "Point B"]
    assert result.rejected_challenges == []
