"""Applicant personal data and opaque ids (ADR-0014): encrypted at rest, masked by default,
revealed only to whoever works the case with an audited reason, and never in URLs, logs or audit."""

from datetime import date

import pytest
from identity.repository import IdentityRepository
from infrastructure.persistence.models.sqlalchemy_models import (
    ApplicantIdentity,
    ApplicationStatusLog,
    LoanApplication,
)
from loguru import logger
from sqlalchemy import select

NAME, CITIZEN_ID, PHONE = "Phạm Thị Riêng Tư", "036195004321", "0987654321"


@pytest.fixture
def captured_logs():
    lines: list[str] = []
    sink = logger.add(lambda message: lines.append(str(message)), level="DEBUG")
    yield lines
    logger.remove(sink)


@pytest.fixture
async def case(db_session, test_app):
    """A staff application entered by off-1 at HN01, in manual review, with a stored identity."""
    ref = await IdentityRepository(db_session, test_app.state.cipher).resolve_or_create(NAME, CITIZEN_ID, PHONE)
    row = LoanApplication(
        sk_id_curr=ref, birth_date=date(1995, 4, 2), amt_income_total=180_000_000, amt_credit=40_000_000,
        name_income_type="Working", name_education_type="Higher education", name_family_status="Married",
        name_housing_type="House / apartment", channel="staff", created_by_sub="off-1", branch_id="HN01",
    )
    db_session.add(row)
    db_session.add(ApplicationStatusLog(sk_id_curr=ref, status="manual_review", created_by="decision-recorder",
                                        event_metadata={"reason_codes": ["INCOME_LOW"]}))
    await db_session.commit()
    return str(row.public_id)


async def test_identity_is_encrypted_at_rest(case, db_session):
    stored = (await db_session.execute(select(ApplicantIdentity))).scalar_one()
    columns = " ".join(str(getattr(stored, c.key)) for c in ApplicantIdentity.__table__.columns)
    assert CITIZEN_ID not in columns and PHONE not in columns and "Riêng" not in columns
    assert stored.citizen_id_last3 == "321" and len(stored.citizen_id_hmac) == 64


async def test_application_shows_name_and_masked_numbers(api_client, act_as, case):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.get(f"/api/v1/applications/{case}")
    assert resp.status_code == 200 and resp.headers["cache-control"] == "no-store"
    body = resp.json()
    assert body["id"] == case and "sk_id_curr" not in body
    assert body["applicant"] == {"full_name": NAME, "citizen_id_masked": "••• ••• ••• 321",
                                 "phone_masked": "•••• ••• 321"}


@pytest.mark.parametrize("guess", ["100002", "not-a-uuid", "00000000-0000-4000-8000-000000000000"])
async def test_unknown_or_malformed_ids_all_look_the_same(api_client, act_as, case, guess):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.get(f"/api/v1/applications/{guess}")
    assert resp.status_code == 404 and resp.json()["detail"] == "Application not found"


async def test_officer_handling_the_case_reveals_with_an_audited_reason(api_client, act_as, case, audit,
                                                                        captured_logs):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    reason = "Customer at the counter, confirming the phone number"
    resp = await api_client.post(f"/api/v1/applications/{case}/identity:reveal", json={"reason": reason})
    assert resp.status_code == 200 and resp.headers["cache-control"] == "no-store"
    assert resp.json() == {"full_name": NAME, "citizen_id": CITIZEN_ID, "phone": PHONE}
    event = [e for e in audit.events if e["action"] == "reveal_identity"][-1]
    assert event["outcome"] == "allowed" and event["details"]["reason"] == reason
    assert CITIZEN_ID not in str(audit.events) and PHONE not in str(audit.events)
    assert not any(CITIZEN_ID in line or PHONE in line for line in captured_logs)


async def test_reveal_needs_a_reason(api_client, act_as, case):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.post(f"/api/v1/applications/{case}/identity:reveal", json={"reason": "why"})
    assert resp.status_code == 422


@pytest.mark.parametrize("who", [
    ("au-1", "staff", {"auditor"}, None),
    ("off-2", "staff", {"loan_officer"}, "HCM02"),
    ("off-3", "staff", {"loan_officer"}, "HN01"),  # same branch, but not their case
    ("rm-1", "staff", {"risk_manager"}, None),
])
async def test_reveal_is_refused_to_everyone_else(api_client, act_as, case, audit, who):
    act_as(*who)
    resp = await api_client.post(f"/api/v1/applications/{case}/identity:reveal",
                                 json={"reason": "Just checking this customer"})
    assert resp.status_code == 403
    assert audit.events[-1]["outcome"] == "denied" and audit.events[-1]["action"] == "reveal_identity"


async def test_underwriter_reveals_only_while_in_manual_review(api_client, act_as, case, db_session):
    act_as("uw-1", "staff", {"underwriter"})
    body = {"reason": "Calling the customer about payslips"}
    assert (await api_client.post(f"/api/v1/applications/{case}/identity:reveal", json=body)).status_code == 200
    ref = (await db_session.execute(select(LoanApplication.sk_id_curr))).scalar_one()
    db_session.add(ApplicationStatusLog(sk_id_curr=ref, status="approved", created_by="uw-2"))
    await db_session.commit()
    assert (await api_client.post(f"/api/v1/applications/{case}/identity:reveal", json=body)).status_code == 403


async def test_submission_stores_identity_and_never_logs_or_audits_it(api_client, act_as, valid_payload, audit,
                                                                      db_session, captured_logs):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.post("/api/v1/applications", json=valid_payload)
    assert resp.status_code == 201
    assert (await db_session.execute(select(ApplicantIdentity))).scalar_one().phone_last3 == "123"
    secrets = ("001099000123", "0900000123", "Nguyễn Văn Thử")
    assert not any(s in str(audit.events) for s in secrets)
    assert not any(s in line for line in captured_logs for s in secrets)


@pytest.mark.parametrize("field, value", [("citizen_id", "12345"), ("phone", "12"), ("full_name", "A")])
async def test_identity_is_validated(api_client, act_as, valid_payload, field, value):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    valid_payload["applicant"][field] = value
    assert (await api_client.post("/api/v1/applications", json=valid_payload)).status_code == 422


async def test_applicant_lists_only_their_own_applications(api_client, act_as, db_session, case):
    db_session.add(LoanApplication(
        sk_id_curr="S9", birth_date=date(1990, 1, 1), amt_income_total=1, amt_credit=25_000_000,
        name_income_type="Working", name_education_type="Higher education", name_family_status="Married",
        name_housing_type="House / apartment", channel="self", applicant_sub="cust-a", created_by_sub="cust-a"))
    await db_session.commit()
    act_as("cust-a", "customers", {"applicant"})
    mine = (await api_client.get("/api/v1/me/applications")).json()
    assert [a["amt_credit"] for a in mine] == [25_000_000] and mine[0]["status"] == "submitted"
    assert mine[0]["id"] != case
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    assert (await api_client.get("/api/v1/me/applications")).status_code == 403


async def test_decision_has_a_timeline_without_internals(api_client, act_as, case):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    body = (await api_client.get(f"/api/v1/applications/{case}/decision")).json()
    assert [h["status"] for h in body["history"]] == ["submitted", "manual_review"]
    assert set(body["history"][0]) == {"status", "at"}
    assert body["reasons"][0]["code"] == "INCOME_LOW" and body["amt_credit"] == 40_000_000


# --- documents ------------------------------------------------------------------------------

async def test_self_service_needs_both_sides_of_the_id_card(api_client, act_as, valid_payload, upload):
    act_as("cust-z", "customers", {"applicant"})
    valid_payload["document_ids"] = {"document_id_2": upload("cust-z")}
    resp = await api_client.post("/api/v1/applications", json=valid_payload)
    assert resp.status_code == 422 and resp.json()["detail"]["slots"] == ["document_id_15"]


async def test_someone_elses_document_is_refused(api_client, act_as, valid_payload, upload):
    act_as("cust-z", "customers", {"applicant"})
    valid_payload["document_ids"] = {"document_id_2": upload("cust-other"), "document_id_15": upload("cust-z", 15)}
    resp = await api_client.post("/api/v1/applications", json=valid_payload)
    assert resp.status_code == 403 and resp.json()["detail"]["error"] == "document_not_owned"


async def test_a_document_that_was_never_uploaded_is_refused(api_client, act_as, valid_payload, test_app):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    owner = test_app.state.cipher.owner_tag("off-1")
    valid_payload["document_ids"] = {"document_id_3": f"{owner}/financial/income/doc_{'a' * 32}.pdf"}
    resp = await api_client.post("/api/v1/applications", json=valid_payload)
    assert resp.status_code == 422 and resp.json()["detail"]["error"] == "document_not_uploaded"


async def test_unknown_document_slots_are_rejected(api_client, act_as, valid_payload, upload):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    valid_payload["document_ids"] = {"passport": upload("off-1")}
    assert (await api_client.post("/api/v1/applications", json=valid_payload)).status_code == 422


async def test_applicant_attaches_payslips_while_the_file_is_open(api_client, act_as, db_session, upload, audit):
    row = LoanApplication(
        sk_id_curr="S7", birth_date=date(1990, 1, 1), amt_income_total=1, amt_credit=25_000_000,
        name_income_type="Working", name_education_type="Higher education", name_family_status="Married",
        name_housing_type="House / apartment", channel="self", applicant_sub="cust-a", created_by_sub="cust-a")
    db_session.add(row)
    db_session.add(ApplicationStatusLog(sk_id_curr="S7", status="manual_review", created_by="decision-recorder"))
    await db_session.commit()
    act_as("cust-a", "customers", {"applicant"})
    url = f"/api/v1/applications/{row.public_id}/documents"
    assert (await api_client.post(url, json={"slot": 3, "document_id": upload("cust-a", 3)})).status_code == 201
    assert (await api_client.get(f"/api/v1/applications/{row.public_id}")).json()["documents"] == ["document_id_3"]
    # someone else's upload, or someone else's file
    assert (await api_client.post(url, json={"slot": 3, "document_id": upload("cust-b", 3)})).status_code == 403
    act_as("cust-b", "customers", {"applicant"})
    assert (await api_client.post(url, json={"slot": 3, "document_id": upload("cust-b", 3)})).status_code == 403
    # closed files take no more documents
    db_session.add(ApplicationStatusLog(sk_id_curr="S7", status="rejected", created_by="uw-1"))
    await db_session.commit()
    act_as("cust-a", "customers", {"applicant"})
    resp = await api_client.post(url, json={"slot": 3, "document_id": upload("cust-a", 3)})
    assert resp.status_code == 403 and resp.json()["detail"]["rule"] == "own_open"


@pytest.fixture
def log_records():
    records: list[dict] = []
    sink = logger.add(lambda message: records.append(message.record), level="DEBUG")
    yield records
    logger.remove(sink)


def _events(records, name):
    return [r["extra"] for r in records if r["extra"].get("event") == name]


async def test_revealing_identity_leaves_named_log_events_without_the_values(api_client, act_as, case, log_records):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.post(f"/api/v1/applications/{case}/identity:reveal",
                                 json={"reason": "Customer at the counter, confirming the phone number"})
    assert resp.status_code == 200
    (accessed,) = _events(log_records, "identity.pii.accessed")
    assert accessed["status"] == "SUCCESS" and accessed["action"] == "reveal_identity"
    assert accessed["actor"]["id"] == "off-1" and accessed["target"]["id"] == case
    assert accessed["fields_accessed"] == ["citizen_id", "phone"]
    allowed = [e for e in _events(log_records, "authz.access.allowed") if e["action"] == "reveal_identity"]
    assert len(allowed) == 1
    everything = str([r["message"] for r in log_records]) + str([r["extra"] for r in log_records])
    assert CITIZEN_ID not in everything and PHONE not in everything and "Riêng" not in everything


async def test_an_officer_from_another_branch_leaves_a_denied_event_and_no_reveal(api_client, act_as, case, log_records):
    act_as("off-2", "staff", {"loan_officer"}, "HN02")
    resp = await api_client.post(f"/api/v1/applications/{case}/identity:reveal", json={"reason": "Wanted to look at a colleague case, no work reason"})
    assert resp.status_code in (403, 404)
    assert _events(log_records, "identity.pii.accessed") == []
    if resp.status_code == 403:
        (denied,) = _events(log_records, "authz.access.denied")
        assert denied["status"] == "DENIED" and denied["actor"]["id"] == "off-2"
