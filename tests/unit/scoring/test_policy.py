"""Decision policy (E5): bands, statuses and the no-auto-approve fallback."""

import pytest

from scoring.policy import Decision, DecisionBand, DecisionPolicy


@pytest.fixture
def policy():
    return DecisionPolicy(approve_below=0.25, reject_above=0.35)


@pytest.mark.parametrize(
    "score, band, status",
    [
        (0.0, DecisionBand.APPROVE, "approved"),
        (0.2499, DecisionBand.APPROVE, "approved"),
        (0.25, DecisionBand.UNDER_REVIEW, "manual_review"),
        (0.30, DecisionBand.UNDER_REVIEW, "manual_review"),
        (0.35, DecisionBand.UNDER_REVIEW, "manual_review"),
        (0.3501, DecisionBand.REJECT, "rejected"),
        (1.0, DecisionBand.REJECT, "rejected"),
    ],
)
def test_bands(policy, score, band, status):
    decision = policy.decide(score)
    assert decision.band is band
    assert decision.status == status
    assert decision.reasons == ("score_band",)


def test_approvals_carry_no_reason_codes(policy):
    assert policy.decide(0.1, ["EXT_SCORE_LOW"]).reason_codes == ()


def test_adverse_decisions_keep_at_most_four_reason_codes_in_order(policy):
    codes = ["A", "B", "C", "D", "E"]
    assert policy.decide(0.9, codes).reason_codes == ("A", "B", "C", "D")
    assert policy.decide(0.3, codes[:2]).reason_codes == ("A", "B")


def test_unavailable_score_goes_to_manual_review(policy):
    decision = policy.decide_unavailable("scoring_unavailable")
    assert decision.status == "manual_review"
    assert decision.score is None
    assert decision.reasons == ("scoring_unavailable",)


@pytest.mark.parametrize("approve_below, reject_above", [(0, 0.3), (0.4, 0.3), (0.2, 1.0)])
def test_invalid_bands_are_rejected(approve_below, reject_above):
    with pytest.raises(ValueError):
        DecisionPolicy(approve_below=approve_below, reject_above=reject_above)


@pytest.mark.parametrize("score", [-0.01, 1.01])
def test_scores_outside_unit_interval_are_rejected(policy, score):
    with pytest.raises(ValueError):
        policy.decide(score)


def test_event_fields():
    fields = Decision(DecisionBand.REJECT, 0.5, ("score_band",), ("EXT_SCORE_LOW",)).to_event_fields()
    assert fields == {
        "band": "REJECT",
        "status": "rejected",
        "score": 0.5,
        "reasons": ["score_band"],
        "reason_codes": ["EXT_SCORE_LOW"],
    }
