"""Permission matrix (E11 §5, ADR-0013): allow and deny cases per role."""

import pytest

from authz import Action, Principal, Resource, authorize
from authz.policy import rules_table

APPLICANT = Principal("cust-a", "customers", frozenset({"applicant"}))
OTHER_APPLICANT = Principal("cust-b", "customers", frozenset({"applicant"}))
OFFICER = Principal("off-1", "staff", frozenset({"loan_officer"}), "HN01")
OFFICER_OTHER_BRANCH = Principal("off-2", "staff", frozenset({"loan_officer"}), "HCM02")
UNDERWRITER = Principal("uw-1", "staff", frozenset({"underwriter"}))
RISK = Principal("rm-1", "staff", frozenset({"risk_manager"}))
RISK_2 = Principal("rm-2", "staff", frozenset({"risk_manager"}))
AUDITOR = Principal("au-1", "staff", frozenset({"auditor"}))
ADMIN = Principal("ad-1", "staff", frozenset({"admin"}))

SELF_APP = Resource(id="1", channel="self", applicant_sub="cust-a", status="manual_review")
STAFF_APP = Resource(
    id="2", channel="staff", created_by_sub="off-1", branch_id="HN01", status="manual_review", consent_recorded=True
)


def allowed(principal, action, resource):
    return authorize(principal, action, resource).allowed


@pytest.mark.parametrize(
    "principal, action, resource, expected",
    [
        # submit
        (APPLICANT, Action.SUBMIT_APPLICATION, SELF_APP, True),
        (OTHER_APPLICANT, Action.SUBMIT_APPLICATION, SELF_APP, False),
        (OFFICER, Action.SUBMIT_APPLICATION, STAFF_APP, True),
        (OFFICER_OTHER_BRANCH, Action.SUBMIT_APPLICATION, STAFF_APP, False),
        (UNDERWRITER, Action.SUBMIT_APPLICATION, STAFF_APP, False),
        # read application (PII)
        (APPLICANT, Action.READ_APPLICATION, SELF_APP, True),
        (OTHER_APPLICANT, Action.READ_APPLICATION, SELF_APP, False),
        (OFFICER, Action.READ_APPLICATION, STAFF_APP, True),
        (OFFICER_OTHER_BRANCH, Action.READ_APPLICATION, STAFF_APP, False),
        (UNDERWRITER, Action.READ_APPLICATION, STAFF_APP, True),
        (UNDERWRITER, Action.READ_APPLICATION, Resource(status="approved"), False),
        (RISK, Action.READ_APPLICATION, STAFF_APP, False),
        (AUDITOR, Action.READ_APPLICATION, STAFF_APP, False),
        (ADMIN, Action.READ_APPLICATION, STAFF_APP, False),
        # internal factors
        (OFFICER, Action.READ_CUSTOMER_PROFILE, STAFF_APP, True),
        (OFFICER, Action.READ_CUSTOMER_PROFILE, Resource(created_by_sub="off-1", consent_recorded=False), False),
        (OFFICER, Action.READ_CUSTOMER_PROFILE, Resource(created_by_sub="off-9", consent_recorded=True), False),
        (UNDERWRITER, Action.READ_CUSTOMER_PROFILE, STAFF_APP, True),
        (APPLICANT, Action.READ_CUSTOMER_PROFILE, SELF_APP, False),
        # lookups by exact ID with a purpose
        (OFFICER, Action.LOOKUP_CUSTOMER, Resource(type="customer", purpose="co_applicant"), True),
        (OFFICER, Action.LOOKUP_CUSTOMER, Resource(type="customer", purpose="curiosity"), False),
        (OFFICER, Action.LOOKUP_CUSTOMER, Resource(type="customer"), False),
        (UNDERWRITER, Action.LOOKUP_CUSTOMER, Resource(type="customer", purpose="co_applicant"), False),
        # decisions and explanations
        (APPLICANT, Action.READ_DECISION, SELF_APP, True),
        (OTHER_APPLICANT, Action.READ_DECISION, SELF_APP, False),
        (OFFICER, Action.READ_DECISION, STAFF_APP, True),
        (AUDITOR, Action.READ_DECISION, STAFF_APP, True),
        (APPLICANT, Action.READ_EXPLANATION, SELF_APP, False),
        (OFFICER, Action.READ_EXPLANATION, STAFF_APP, False),
        (UNDERWRITER, Action.READ_EXPLANATION, STAFF_APP, True),
        (RISK, Action.READ_EXPLANATION, STAFF_APP, False),
        (AUDITOR, Action.READ_EXPLANATION, STAFF_APP, True),
        # maker-checker: officers never decide; underwriters never review their own submissions
        (OFFICER, Action.REVIEW_DECISION, STAFF_APP, False),
        (UNDERWRITER, Action.CLAIM_REVIEW, STAFF_APP, True),
        (UNDERWRITER, Action.REVIEW_DECISION, Resource(created_by_sub="uw-1", status="manual_review"), False),
        (UNDERWRITER, Action.REVIEW_DECISION, Resource(created_by_sub="off-1", status="approved"), False),
        # four eyes on policy changes
        (RISK, Action.PROPOSE_POLICY_CHANGE, Resource(type="policy"), True),
        (RISK, Action.APPROVE_POLICY_CHANGE, Resource(type="policy", proposed_by="rm-1"), False),
        (RISK_2, Action.APPROVE_POLICY_CHANGE, Resource(type="policy", proposed_by="rm-1"), True),
        (UNDERWRITER, Action.PROPOSE_POLICY_CHANGE, Resource(type="policy"), False),
        # audit
        (AUDITOR, Action.READ_AUDIT, Resource(type="audit"), True),
        (ADMIN, Action.READ_AUDIT, Resource(type="audit"), False),
        (RISK, Action.READ_AUDIT, Resource(type="audit"), False),
    ],
)
def test_matrix(principal, action, resource, expected):
    assert allowed(principal, action, resource) is expected


def test_denials_name_the_rule():
    decision = authorize(UNDERWRITER, Action.REVIEW_DECISION, Resource(created_by_sub="uw-1", status="manual_review"))
    assert (decision.allowed, decision.rule) == (False, "separation_of_duties")
    assert authorize(APPLICANT, Action.READ_AUDIT, Resource()).rule == "role"


@pytest.mark.parametrize(
    "realm, roles",
    [("customers", {"loan_officer"}), ("staff", {"applicant"}), ("partners", {"applicant"})],
)
def test_roles_cannot_cross_realms(realm, roles):
    with pytest.raises(ValueError):
        Principal("x", realm, frozenset(roles))


def test_every_action_has_at_least_one_rule():
    from authz import Action as A

    assert set(rules_table()) == {a.value for a in A}
