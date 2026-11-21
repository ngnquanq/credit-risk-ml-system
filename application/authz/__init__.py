"""Authorization: the only place that decides what a caller may do (E11, ADR-0013)."""

from .policy import Action, AuthzDecision, Principal, Resource, authorize

__all__ = ["Action", "AuthzDecision", "Principal", "Resource", "authorize"]
