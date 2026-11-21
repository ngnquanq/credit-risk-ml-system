"""Fallback decisions when no score exists (E15).

The rule is deliberately tiny: whatever went wrong, the application goes to a human.
Nothing on a fallback path may approve or reject. ``FallbackDecision`` cannot
represent any other status, so an automatic approval cannot be introduced here by
accident.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

MANUAL_REVIEW = "manual_review"
FEATURES_INCOMPLETE = "features_incomplete"
SCORING_UNAVAILABLE = "scoring_unavailable"


@dataclass(frozen=True)
class FallbackDecision:
    reason: str
    detail: dict

    @property
    def status(self) -> str:
        return MANUAL_REVIEW


def for_timeout(missing_groups: Iterable[str]) -> FallbackDecision:
    """Readiness timed out before every feature group arrived (E3)."""
    return FallbackDecision(FEATURES_INCOMPLETE, {"missing_groups": sorted(set(missing_groups))})


def for_dead_letter(error: str | None) -> FallbackDecision:
    """Scoring failed after all delivery retries (dead-lettered event)."""
    return FallbackDecision(SCORING_UNAVAILABLE, {"error": (error or "unknown")[:500]})
