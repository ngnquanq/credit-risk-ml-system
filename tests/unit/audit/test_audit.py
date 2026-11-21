"""Audit trail (E13): sanitising, hash chain and tamper detection."""

import pytest

from audit import AuditEvent, InMemoryAuditWriter, sanitize, verify_chain


def _event(action="read_application", outcome="allowed", **details):
    return AuditEvent(
        actor_sub="off-1",
        actor_realm="staff",
        actor_roles=("loan_officer",),
        action=action,
        resource_type="application",
        resource_id="100002",
        outcome=outcome,
        details=details,
    )


def test_personal_data_never_enters_details():
    clean = sanitize("submit_application", {"channel": "staff", "full_name": "Nguyễn Văn An", "phone": "09..."})
    assert clean == {"channel": "staff"}


def test_long_text_is_truncated():
    assert len(sanitize("review_decision", {"reason": "x" * 2000})["reason"]) == 500


def test_unknown_outcome_is_rejected():
    with pytest.raises(ValueError):
        _event(outcome="maybe")


async def test_chain_verifies_and_detects_tampering():
    writer = InMemoryAuditWriter()
    for i in range(5):
        await writer.record(_event(rule=f"r{i}"))
    assert verify_chain(writer.rows) is None

    row_id, prev, stored, record = writer.rows[2]
    tampered = list(writer.rows)
    tampered[2] = (row_id, prev, stored, {**record, "outcome": "denied"})
    assert verify_chain(tampered) == 3

    deleted = writer.rows[:1] + writer.rows[2:]
    assert verify_chain(deleted) == 3


async def test_roles_are_recorded_in_a_stable_order():
    writer = InMemoryAuditWriter()
    await writer.record(
        AuditEvent("x", "staff", ("underwriter", "auditor"), "read_audit", "audit", "-", "allowed")
    )
    assert writer.events[0]["actor_roles"] == ["auditor", "underwriter"]
