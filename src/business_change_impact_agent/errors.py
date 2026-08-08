"""Project-specific exceptions."""

from __future__ import annotations


class ImpactAgentError(Exception):
    """Base exception for controlled project failures."""


class ValidationError(ImpactAgentError):
    """Raised when evidence, graph or command input is invalid."""


class SecurityBoundaryError(ImpactAgentError):
    """Raised when a filesystem or authority boundary is violated."""


class ReviewConflictError(ImpactAgentError):
    """Raised when a review is stale, replayed, expired or concurrent."""
