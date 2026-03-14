"""Evidence gathering and formatting package.

Provides gather_evidence() for parallel evidence collection from
decomposition, research, and user-supplied sources.
"""

from sat.evidence.gatherer import gather_evidence

__all__ = ["gather_evidence"]
