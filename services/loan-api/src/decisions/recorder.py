"""Decision recorder (E5, E15): one status row per decision, timeout or dead letter.

Pure of Kafka: ``entrypoints/decision_recorder.py`` owns the consumer loop and
commits offsets only after ``handle*`` returns.
"""

from __future__ import annotations

from typing import Callable, Optional

from loguru import logger

from . import fallback
from .status_log import RecordResult, StatusLogWriter, StatusRow

CREATED_BY = "decision-recorder"
# Fields copied from the scoring event into the status row's metadata.
_DECISION_METADATA = (
    "band", "score", "reasons", "reason_codes", "bands", "model", "model_version",
    "feature_set_sha256", "decided_at",
)

AuditHook = Callable[[str, str, dict], None]  # (action, sk_id_curr, details)


class DecisionRecorder:
    def __init__(self, writer: StatusLogWriter, audit: Optional[AuditHook] = None):
        self._writer = writer
        self._audit = audit

    def handle_decision(self, event: dict) -> RecordResult:
        status = event.get("status")
        if status not in {"approved", "rejected", "manual_review"}:
            raise ValueError(f"Decision event {event.get('event_id')} has invalid status {status!r}")
        metadata = {k: event[k] for k in _DECISION_METADATA if k in event}
        return self._record(event["event_id"], str(event["sk_id_curr"]), status, metadata, "decision")

    def handle_timeout(self, event: dict) -> RecordResult:
        decision = fallback.for_timeout(event.get("missing_groups", ()))
        return self._fallback(event, decision)

    def handle_dead_letter(self, event: dict, event_id: str) -> RecordResult:
        decision = fallback.for_dead_letter(event.get("error"))
        return self._fallback({**event, "event_id": event_id}, decision)

    def _fallback(self, event: dict, decision: fallback.FallbackDecision) -> RecordResult:
        metadata = {"reasons": [decision.reason], **decision.detail}
        return self._record(
            event["event_id"], str(event["sk_id_curr"]), decision.status, metadata, "decision_fallback"
        )

    def _record(self, event_id: str, sk_id_curr: str, status: str, metadata: dict, action: str) -> RecordResult:
        # Audit first: a retry after a crash reproduces both, and the status insert is idempotent.
        if self._audit is not None:
            self._audit(action, sk_id_curr, {"status": status, "event_id": event_id, **metadata})
        row = StatusRow(event_id=event_id, sk_id_curr=sk_id_curr, status=status, created_by=CREATED_BY, metadata=metadata)
        result = self._writer.insert_once(row)
        self._log(result, event_id, sk_id_curr, status, metadata, action)
        return result

    @staticmethod
    def _log(result: RecordResult, event_id: str, sk_id_curr: str, status: str, metadata: dict, action: str) -> None:
        who = {"id": CREATED_BY, "type": "service"}
        what = {"type": "application", "id": sk_id_curr}
        common = dict(actor=who, target=what, action="record_decision", sk_id_curr=sk_id_curr,
                      model_version=metadata.get("model_version"), event_id=event_id, outcome=status, result=result.value)
        common = {k: v for k, v in common.items() if v is not None}
        if action == "decision":
            logger.info("Decision recorded", event="decisions.recorded", status="SUCCESS", **common)
        else:
            reasons = metadata.get("reasons") or ["unknown"]
            logger.warning("Fallback decision recorded", event="decisions.fallback.applied", status="SUCCESS",
                           reason_code=str(reasons[0])[:60], **common)
