"""Shared test helpers and doubles for the SAT test suite.

Importable as ``from tests.helpers import MockProvider`` from any test file.
The project root is on Python's path via ``pythonpath = ["src", "."]`` in
pyproject.toml, which makes the ``tests`` package importable without pytest
magic.

@decision DEC-TEST-HELPERS-001
@title Centralise MockProvider in tests/helpers.py, not conftest
@status accepted
@rationale ``tests/conftest.py`` is loaded by pytest but is NOT a regular
Python module -- importing it directly (``from tests.conftest import ...``)
is a pytest anti-pattern that breaks when the project root is not on sys.path.
Moving shared test doubles to ``tests/helpers.py`` gives them a stable,
importable path that works both from tests and from interactive shells.
"""

from __future__ import annotations

from sat.models.base import ArtifactResult
from sat.providers.base import LLMMessage, LLMResult, LLMUsage


class MockProvider:
    """In-memory LLM provider that returns canned responses.

    Use this anywhere an ``LLMProvider`` protocol implementation is needed
    without hitting a real API.  Configure the responses at construction time:

    .. code-block:: python

        mock = MockProvider(text_response="Hello")
        mock = MockProvider(structured_response=some_artifact_result)
    """

    def __init__(
        self,
        structured_response: ArtifactResult | None = None,
        text_response: str = "{}",
    ) -> None:
        self._structured_response = structured_response
        self._text_response = text_response

    async def generate(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> LLMResult:
        return LLMResult(
            text=self._text_response,
            usage=LLMUsage(input_tokens=100, output_tokens=50),
        )

    async def generate_structured(
        self,
        system_prompt: str,
        messages: list[LLMMessage],
        output_schema: type,
        max_tokens: int = 4096,
        temperature: float = 0.3,
    ) -> ArtifactResult:
        if self._structured_response is not None:
            return self._structured_response
        raise RuntimeError("No structured response configured in MockProvider")
