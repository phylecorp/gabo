"""Tests for _SourceAssessment JSON string parsing.

@decision DEC-VERIFY-005: _SourceAssessment model_validator for JSON string coercion.
@title Test JSON string parsing in _SourceAssessment before Pydantic validation
@status accepted
@rationale Anthropic structured output sometimes returns list fields as JSON strings
instead of native lists. The model_validator pre-parses these so Pydantic can
validate the actual structure. These tests cover the normal, string-encoded, and
invalid-string cases.
"""

from __future__ import annotations

import json

import pytest

from sat.research.verification.assessor import _SourceAssessment


class TestSourceAssessmentParsing:
    def test_parses_normal_dict(self):
        """Normal dict with a list of assessments parses correctly."""
        data = {
            "assessments": [
                {
                    "claim": "The sky is blue",
                    "verdict": "SUPPORTED",
                    "confidence": "High",
                    "reasoning": "Source confirms it.",
                }
            ]
        }
        result = _SourceAssessment(**data)
        assert len(result.assessments) == 1
        assert result.assessments[0].claim == "The sky is blue"
        assert result.assessments[0].verdict == "SUPPORTED"

    def test_parses_string_encoded_assessments(self):
        """String-encoded JSON list for 'assessments' is parsed before validation."""
        items = [
            {
                "claim": "Inflation rose 4%",
                "verdict": "PARTIALLY_SUPPORTED",
                "confidence": "Medium",
                "reasoning": "Source mentions ~4.1%.",
            }
        ]
        data = {"assessments": json.dumps(items)}
        result = _SourceAssessment(**data)
        assert len(result.assessments) == 1
        assert result.assessments[0].verdict == "PARTIALLY_SUPPORTED"

    def test_invalid_json_string_fails_validation(self):
        """A non-parseable string passes through and causes a Pydantic validation error."""
        data = {"assessments": "this is not json"}
        with pytest.raises(Exception):
            _SourceAssessment(**data)
