"""Decision recorder (E5) and fallback rules (E15)."""

import pytest

from decisions import fallback
from decisions.recorder import DecisionRecorder
from decisions.status_log import InMemoryStatusLogWriter, RecordResult, StatusRow


def _decision(event_id="e1", status="manual_review", **extra):
    return {
        "event_id": event_id,
        "sk_id_curr": "100002",
        "band": "UNDER_REVIEW",
        "status": status,
        "score": 0.31,
        "reasons": ["score_band"],
        "reason_codes": ["EXT_SCORE_LOW"],
        "model_version": "7",
        "feature_set_sha256": "9f2c",
        **extra,
    }


@pytest.fixture
def writer():
    return InMemoryStatusLogWriter(known_applications={"100002"})


def test_decision_is_recorded_once(writer):
    recorder = DecisionRecorder(writer)
    assert recorder.handle_decision(_decision()) is RecordResult.INSERTED
    assert recorder.handle_decision(_decision()) is RecordResult.DUPLICATE
    assert len(writer.rows) == 1
    row = writer.rows[0]
    assert row.status == "manual_review"
    assert row.created_by == "decision-recorder"
    assert row.metadata["reason_codes"] == ["EXT_SCORE_LOW"]
    assert row.metadata["feature_set_sha256"] == "9f2c"


def test_unknown_application_is_reported(writer):
    event = {**_decision(), "sk_id_curr": "999"}
    assert DecisionRecorder(writer).handle_decision(event) is RecordResult.UNKNOWN_APPLICATION
    assert writer.rows == []


def test_decision_with_invalid_status_is_rejected(writer):
    with pytest.raises(ValueError):
        DecisionRecorder(writer).handle_decision(_decision(status="maybe"))


def test_timeout_goes_to_manual_review(writer):
    result = DecisionRecorder(writer).handle_timeout(
        {"event_id": "t1", "sk_id_curr": "100002", "missing_groups": ["dwh", "external", "dwh"]}
    )
    assert result is RecordResult.INSERTED
    row = writer.rows[0]
    assert row.status == "manual_review"
    assert row.metadata == {"reasons": ["features_incomplete"], "missing_groups": ["dwh", "external"]}


def test_dead_letter_goes_to_manual_review(writer):
    DecisionRecorder(writer).handle_dead_letter({"sk_id_curr": "100002", "error": "502"}, "dlq:0:42")
    row = writer.rows[0]
    assert (row.event_id, row.status) == ("dlq:0:42", "manual_review")
    assert row.metadata["reasons"] == ["scoring_unavailable"]


@pytest.mark.parametrize(
    "decision",
    [fallback.for_timeout([]), fallback.for_timeout(["application"]), fallback.for_dead_letter(None),
     fallback.for_dead_letter("x" * 10_000)],
)
def test_fallback_never_approves(decision):
    assert decision.status == "manual_review"


def test_audit_hook_sees_every_decision(writer):
    seen = []
    recorder = DecisionRecorder(writer, audit=lambda action, sk, details: seen.append((action, sk, details["status"])))
    recorder.handle_decision(_decision())
    recorder.handle_timeout({"event_id": "t1", "sk_id_curr": "100002"})
    assert seen == [("decision", "100002", "manual_review"), ("decision_fallback", "100002", "manual_review")]


def test_status_row_rejects_non_decision_statuses():
    with pytest.raises(ValueError):
        StatusRow(event_id="e", sk_id_curr="1", status="submitted", created_by="x")
    with pytest.raises(ValueError):
        StatusRow(event_id="", sk_id_curr="1", status="approved", created_by="x")
