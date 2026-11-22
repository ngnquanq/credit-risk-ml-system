"""API access control (E11 AC1–AC12, ADR-0013) with audited decisions (E13)."""

from datetime import date, datetime

import pytest

from infrastructure.persistence.models.sqlalchemy_models import ApplicationStatusLog, LoanApplication


async def _application(db, sk, **kw):
    row = LoanApplication(
        sk_id_curr=sk,
        birth_date=date(1991, 3, 14),
        amt_income_total=15_000_000,
        amt_credit=40_000_000,
        name_income_type="Working",
        name_education_type="Higher education",
        name_family_status="Married",
        name_housing_type="House / apartment",
        **kw,
    )
    db.add(row)
    await db.commit()
    return row


async def _status(db, sk, status, created_by="decision-recorder", **meta):
    db.add(ApplicationStatusLog(sk_id_curr=sk, status=status, created_by=created_by, event_metadata=meta,
                                created_at=datetime.utcnow()))
    await db.commit()


@pytest.fixture
async def apps(db_session):
    """Internal key -> public id; URLs only ever carry the public id (ADR-0014)."""
    rows = [
        await _application(db_session, "S1", channel="self", applicant_sub="cust-a", created_by_sub="cust-a"),
        await _application(db_session, "B1", channel="staff", created_by_sub="off-1", branch_id="HN01",
                           bureau_consent_at=datetime.utcnow()),
        await _application(db_session, "B2", channel="staff", created_by_sub="off-2", branch_id="HCM02"),
    ]
    await _status(db_session, "S1", "manual_review", score=0.31, reason_codes=["EXT_SCORE_LOW"],
                  contributions={"EXT_SOURCE_2": 0.84}, model_version="7")
    await _status(db_session, "B1", "manual_review", score=0.30, reason_codes=["INCOME_LOW"])
    return {row.sk_id_curr: str(row.public_id) for row in rows}


async def test_missing_token_is_401(test_app, api_client):
    from entrypoints.api.security import get_principal

    test_app.dependency_overrides.pop(get_principal)
    resp = await api_client.get("/api/v1/applications/00000000-0000-4000-8000-000000000000")
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"].startswith("Bearer")


async def test_applicant_reads_own_but_not_others(api_client, act_as, apps, audit):
    act_as("cust-a", "customers", {"applicant"})
    assert (await api_client.get(f"/api/v1/applications/{apps['S1']}")).status_code == 200
    resp = await api_client.get(f"/api/v1/applications/{apps['B1']}")
    assert resp.status_code == 403
    assert resp.json()["detail"]["rule"] == "own"
    assert audit.events[-1]["outcome"] == "denied" and audit.events[-1]["resource_id"] == apps["B1"]


async def test_loan_officer_is_limited_to_their_branch(api_client, act_as, apps):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    assert (await api_client.get(f"/api/v1/applications/{apps['B1']}")).status_code == 200
    assert (await api_client.get(f"/api/v1/applications/{apps['B2']}")).status_code == 403


async def test_applicant_sees_reasons_but_not_score(api_client, act_as, apps):
    act_as("cust-a", "customers", {"applicant"})
    body = (await api_client.get(f"/api/v1/applications/{apps['S1']}/decision",
                                 headers={"Accept-Language": "en"})).json()
    assert body["status"] == "manual_review"
    assert body["reasons"] == [{"code": "EXT_SCORE_LOW", "text": "External credit scores are low"}]
    assert "score" not in body and "contributions" not in body
    assert (await api_client.get(f"/api/v1/applications/{apps['S1']}/explanation")).status_code == 403


async def test_loan_officer_cannot_see_the_explanation(api_client, act_as, apps):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    assert (await api_client.get(f"/api/v1/applications/{apps['B1']}/decision")).status_code == 200
    assert (await api_client.get(f"/api/v1/applications/{apps['B1']}/explanation")).status_code == 403


async def test_underwriter_sees_the_explanation(api_client, act_as, apps):
    act_as("uw-1", "staff", {"underwriter"})
    body = (await api_client.get(f"/api/v1/applications/{apps['S1']}/explanation")).json()
    assert body["score"] == 0.31 and body["contributions"] == {"EXT_SOURCE_2": 0.84}


async def test_underwriter_cannot_review_own_submission(api_client, act_as, apps):
    act_as("off-1", "staff", {"underwriter"})  # the same person who entered B1
    resp = await api_client.post(f"/api/v1/reviews/{apps['B1']}/decision", json={
        "outcome": "approved", "reason_code": "INCOME_VERIFIED", "reason": "Payslips confirm the income"})
    assert resp.status_code == 403
    assert resp.json()["detail"]["rule"] == "separation_of_duties"


async def test_underwriter_review_is_recorded_and_audited(api_client, act_as, apps, audit):
    act_as("uw-1", "staff", {"underwriter"})
    queue = (await api_client.get("/api/v1/reviews")).json()
    assert {q["application_id"] for q in queue} == {apps["S1"], apps["B1"]}
    resp = await api_client.post(f"/api/v1/reviews/{apps['B1']}/decision", json={
        "outcome": "approved", "reason_code": "INCOME_VERIFIED", "reason": "Payslips confirm the income"})
    assert resp.status_code == 201
    assert (await api_client.get(f"/api/v1/applications/{apps['B1']}/status")).json()["status"] == "approved"
    review = [e for e in audit.events if e["action"] == "review_decision"][-1]
    assert review["outcome"] == "allowed"
    assert review["details"]["to_status"] == "approved"


async def test_loan_officer_cannot_decide(api_client, act_as, apps):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.post(f"/api/v1/reviews/{apps['B1']}/decision", json={
        "outcome": "approved", "reason_code": "X_CODE", "reason": "I know this customer well"})
    assert resp.status_code == 403
    assert (await api_client.get("/api/v1/reviews")).status_code == 403


async def test_status_defaults_to_submitted(api_client, act_as, db_session):
    row = await _application(db_session, "N1", channel="staff", created_by_sub="off-1", branch_id="HN01")
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    assert (await api_client.get(f"/api/v1/applications/{row.public_id}/status")).json()["status"] == "submitted"


async def test_submit_takes_ownership_from_the_token(api_client, act_as, mock_workflow, valid_payload, upload):
    act_as("cust-z", "customers", {"applicant"})
    payload = {**valid_payload, "branch_id": "HN01", "created_by_sub": "someone-else", "sk_id_curr": "100002",
               "document_ids": {"document_id_2": upload("cust-z"), "document_id_15": upload("cust-z", 15)}}
    resp = await api_client.post("/api/v1/applications", json=payload)
    assert resp.status_code == 201
    inputs, ownership = mock_workflow.execute.call_args.args
    assert ownership["channel"] == "self"
    assert ownership["applicant_sub"] == "cust-z"
    assert ownership["branch_id"] is None
    # The internal key comes from the identity store, never from the body.
    assert inputs.sk_id_curr != "100002" and inputs.sk_id_curr.startswith("9")
    assert resp.json() == {"id": ownership["public_id"], "status": "submitted"}


async def test_returning_customer_with_an_application_gets_409(api_client, act_as, valid_payload, test_app,
                                                                db_session):
    from identity.repository import IdentityRepository

    citizen_id = valid_payload["applicant"]["citizen_id"]
    ref = await IdentityRepository(db_session, test_app.state.cipher).resolve_or_create("Nguyễn Văn Thử", citizen_id,
                                                                                         "0900000123")
    await _application(db_session, ref, channel="staff", created_by_sub="off-1", branch_id="HN01")
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.post("/api/v1/applications", json=valid_payload)
    assert resp.status_code == 409
    assert ref not in resp.text


async def test_policy_change_needs_a_second_risk_manager(api_client, act_as, audit):
    act_as("rm-1", "staff", {"risk_manager"})
    created = await api_client.post("/api/v1/policy-changes", json={
        "approve_below": 0.22, "reject_above": 0.33, "rationale": "Cost matrix update for Q1"})
    assert created.status_code == 201
    change_id = created.json()["id"]

    own = await api_client.post(f"/api/v1/policy-changes/{change_id}/decision", json={"approve": True})
    assert own.status_code == 403 and own.json()["detail"]["rule"] == "four_eyes"

    act_as("rm-2", "staff", {"risk_manager"})
    approved = await api_client.post(f"/api/v1/policy-changes/{change_id}/decision", json={"approve": True})
    assert approved.status_code == 200
    assert approved.json()["state"] == "active" and approved.json()["approved_by"] == "rm-2"


async def test_underwriter_cannot_propose_policy(api_client, act_as):
    act_as("uw-1", "staff", {"underwriter"})
    resp = await api_client.post("/api/v1/policy-changes", json={
        "approve_below": 0.2, "reject_above": 0.3, "rationale": "Looser bands please"})
    assert resp.status_code == 403


async def test_auditor_traces_a_decision_and_the_search_is_audited(api_client, act_as, apps):
    act_as("uw-1", "staff", {"underwriter"})
    await api_client.post(f"/api/v1/reviews/{apps['B1']}/decision", json={
        "outcome": "approved", "reason_code": "INCOME_VERIFIED", "reason": "Payslips confirm the income"})
    act_as("au-1", "staff", {"auditor"})
    body = (await api_client.get("/api/v1/audit", params={"resource": f"application:{apps['B1']}"})).json()
    actions = [e["action"] for e in body["events"]]
    assert "review_decision" in actions
    assert actions[-1] == "read_audit"


async def test_only_auditors_read_the_audit_trail(api_client, act_as):
    act_as("rm-1", "staff", {"risk_manager"})
    assert (await api_client.get("/api/v1/audit", params={"resource": "application:B1"})).status_code == 403


@pytest.fixture
def fake_profile(test_app):
    from entrypoints.api.dependencies import get_profile_provider
    from infrastructure.external.customer_profile import summarize

    class Fake:
        async def profile(self, sk_id_curr):
            return summarize({"mart_pos_cash_balance": [{"POS_COUNT_LOANS_TOTAL": 3, "POS_MAX_MAX_DPD": 12}]},
                             {"bureau_active_count": 2})

    async def override():
        return Fake()

    test_app.dependency_overrides[get_profile_provider] = override


async def test_officer_sees_profile_only_for_own_case_with_consent(api_client, act_as, apps, fake_profile, db_session):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    body = (await api_client.get(f"/api/v1/applications/{apps['B1']}/customer-profile")).json()
    assert body["pos_loans"]["count"] == 3 and body["bureau"]["active_credits"] == 2
    # same branch, but entered by someone else
    other = await _application(db_session, "B3", channel="staff", created_by_sub="off-9", branch_id="HN01",
                               bureau_consent_at=datetime.utcnow())
    resp = await api_client.get(f"/api/v1/applications/{other.public_id}/customer-profile")
    assert resp.status_code == 403 and resp.json()["detail"]["rule"] == "handling_application"


async def test_officer_notes_reach_the_underwriter(api_client, act_as, apps, audit):
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    resp = await api_client.post(f"/api/v1/applications/{apps['B1']}/notes", json={"kind": "concern", "text": "ID photo does not match"})
    assert resp.status_code == 201
    act_as("uw-1", "staff", {"underwriter"})
    notes = (await api_client.get(f"/api/v1/applications/{apps['B1']}/notes")).json()
    assert notes[0]["kind"] == "concern"
    flagged = [e for e in audit.events if e["action"] == "flag_concern"][-1]
    assert flagged["details"] == {"rule": "same_branch", "concern_type": "concern"}  # text never audited


async def test_lookup_takes_the_citizen_id_in_the_body_with_a_purpose(api_client, act_as, test_app, audit,
                                                                       db_session):
    from identity.repository import IdentityRepository

    repo = IdentityRepository(db_session, test_app.state.cipher)
    ref = await repo.resolve_or_create("Trần Văn Khách", "079088000555", "0911000555")
    await _application(db_session, ref, channel="staff", created_by_sub="off-2", branch_id="HCM02")
    act_as("off-1", "staff", {"loan_officer"}, "HN01")

    assert (await api_client.post("/api/v1/customers:lookup", json={"citizen_id": "079088000555"})).status_code == 422
    body = (await api_client.post("/api/v1/customers:lookup",
                                  json={"citizen_id": "079 088 000 555", "purpose": "co_applicant"})).json()
    assert body == {"citizen_id_masked": "••• ••• ••• 555", "found": True, "applications": 1,
                    "statuses": ["submitted"], "same_branch": False}
    event = audit.events[-1]
    assert event["details"]["purpose"] == "co_applicant" and event["resource_id"] == ref
    assert "079088000555" not in str(audit.events)


@pytest.mark.parametrize("failure", ["hang", "down"])
async def test_profile_degrades_fast_when_the_warehouse_is_slow_or_down(test_app, api_client, act_as, apps, failure,
                                                                        monkeypatch):
    """Regression: a hanging warehouse call held a DB transaction open and hung the case view (E15)."""
    import asyncio

    from core import settings
    from entrypoints.api.dependencies import get_profile_provider

    monkeypatch.setattr(settings, "profile_timeout_seconds", 0.2)

    class Broken:
        async def profile(self, sk_id_curr):
            if failure == "hang":
                await asyncio.sleep(30)
            raise ConnectionError("warehouse down")

    async def override():
        return Broken()

    test_app.dependency_overrides[get_profile_provider] = override
    act_as("off-1", "staff", {"loan_officer"}, "HN01")
    started = asyncio.get_running_loop().time()
    resp = await api_client.get(f"/api/v1/applications/{apps['B1']}/customer-profile")
    assert resp.status_code == 503
    assert asyncio.get_running_loop().time() - started < 5
