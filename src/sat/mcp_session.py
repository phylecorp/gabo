"""Session state management for MCP server interactions.

Tracks analysis sessions across multiple tool calls. Each session holds the
question, evidence, ordered technique list, accumulated results, and adversarial
exchanges. Sessions live in-memory for the lifetime of the MCP server process.

@decision DEC-MCP-SESSION-001
@title In-memory session store for multi-step MCP interactions
@status accepted
@rationale MCP tools are stateless individual calls. Sessions bridge the gap,
letting a connecting LLM drive the analysis step-by-step (new_session ->
next_prompt -> submit_result -> ... -> synthesis) while the server tracks
accumulated state. In-memory dict is sufficient since MCP servers are
single-process and sessions don't need persistence.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sat.models.adversarial import AdversarialExchange
from sat.models.base import ArtifactResult


@dataclass
class AnalysisSession:
    """State for a multi-step analysis driven via MCP tools."""

    session_id: str
    question: str
    evidence: str | None
    technique_ids: list[str]
    current_index: int = 0
    prior_results: dict[str, ArtifactResult] = field(default_factory=dict)
    adversarial_exchanges: list[AdversarialExchange] = field(default_factory=list)
    completed: bool = False


# In-memory session store keyed by session_id
_sessions: dict[str, AnalysisSession] = {}


def create_session(
    question: str,
    evidence: str | None,
    technique_ids: list[str],
) -> AnalysisSession:
    """Create a new analysis session and register it in the store.

    Args:
        question: The analytic question to investigate.
        evidence: Optional background evidence or context.
        technique_ids: Ordered list of technique IDs to execute.

    Returns:
        The newly created AnalysisSession.
    """
    session_id = uuid.uuid4().hex[:12]
    session = AnalysisSession(
        session_id=session_id,
        question=question,
        evidence=evidence,
        technique_ids=technique_ids,
    )
    _sessions[session_id] = session
    return session


def get_session(session_id: str) -> AnalysisSession:
    """Retrieve an existing session by ID.

    Args:
        session_id: The session identifier returned by create_session.

    Returns:
        The AnalysisSession.

    Raises:
        KeyError: If no session exists with the given ID.
    """
    if session_id not in _sessions:
        raise KeyError(f"Session not found: {session_id}")
    return _sessions[session_id]


def clear_sessions() -> None:
    """Remove all sessions. Primarily for testing."""
    _sessions.clear()
