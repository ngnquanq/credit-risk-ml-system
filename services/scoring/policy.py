"""Decision policy: turns a probability of default into a decision band (E5).

score = P(default); higher is riskier.
    score <  approve_below                 -> APPROVE       (status approved)
    approve_below <= score <= reject_above -> UNDER_REVIEW  (status manual_review)
    score >  reject_above                  -> REJECT        (status rejected)

When the score cannot be computed the policy never approves: the application goes
to manual review with an explicit reason (E15).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence


class DecisionBand(str, Enum):
    APPROVE = "APPROVE"
    UNDER_REVIEW = "UNDER_REVIEW"
    REJECT = "REJECT"


_STATUS = {
    DecisionBand.APPROVE: "approved",
    DecisionBand.UNDER_REVIEW: "manual_review",
    DecisionBand.REJECT: "rejected",
}

SCORE_BAND = "score_band"
FEATURE_DATA_UNAVAILABLE = "feature_data_unavailable"
FEATURES_INCOMPLETE = "features_incomplete"
SCORING_UNAVAILABLE = "scoring_unavailable"


@dataclass(frozen=True)
class Decision:
    band: DecisionBand
    score: float | None
    reasons: tuple[str, ...]
    # Applicant-facing model reason codes (E14); empty for approvals.
    reason_codes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def status(self) -> str:
        return _STATUS[self.band]

    def to_event_fields(self) -> dict:
        return {
            "band": self.band.value,
            "status": self.status,
            "score": self.score,
            "reasons": list(self.reasons),
            "reason_codes": list(self.reason_codes),
        }


@dataclass(frozen=True)
class DecisionPolicy:
    approve_below: float = 0.25
    reject_above: float = 0.35
    max_reason_codes: int = 4

    def __post_init__(self) -> None:
        if not 0 < self.approve_below <= self.reject_above < 1:
            raise ValueError(
                "Decision bands must satisfy 0 < approve_below <= reject_above < 1, "
                f"got approve_below={self.approve_below}, reject_above={self.reject_above}"
            )

    @property
    def bands(self) -> dict:
        return {"approve_below": self.approve_below, "reject_above": self.reject_above}

    def decide(self, score: float, reason_codes: Sequence[str] = ()) -> Decision:
        score = float(score)
        if not 0.0 <= score <= 1.0:
            raise ValueError(f"score must be a probability in [0, 1], got {score}")
        if score < self.approve_below:
            return Decision(DecisionBand.APPROVE, score, (SCORE_BAND,))
        band = DecisionBand.REJECT if score > self.reject_above else DecisionBand.UNDER_REVIEW
        return Decision(band, score, (SCORE_BAND,), tuple(reason_codes)[: self.max_reason_codes])

    def decide_unavailable(self, reason: str = FEATURE_DATA_UNAVAILABLE) -> Decision:
        """No score could be produced: route to a human, never approve."""
        return Decision(DecisionBand.UNDER_REVIEW, None, (reason,))
