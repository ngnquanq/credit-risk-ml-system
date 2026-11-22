"""Permission matrix as code (E11 §5, ADR-0013).

Pure: no I/O and no framework imports. Routes load only the fields a rule needs into a
``Resource``, call ``authorize`` before touching anything else, and audit the result.
Anything not granted by a rule below is denied.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Optional

STAFF_REALM = "staff"
CUSTOMER_REALM = "customers"
STAFF_ROLES = frozenset({"loan_officer", "underwriter", "risk_manager", "auditor", "admin"})
CUSTOMER_ROLES = frozenset({"applicant"})
MANUAL_REVIEW = "manual_review"
LOOKUP_PURPOSES = frozenset({"co_applicant", "guarantor", "customer_present"})


class Action(str, Enum):
    SUBMIT_APPLICATION = "submit_application"
    READ_APPLICATION = "read_application"
    READ_CUSTOMER_PROFILE = "read_customer_profile"
    REVEAL_IDENTITY = "reveal_identity"
    ATTACH_DOCUMENT = "attach_document"
    LOOKUP_CUSTOMER = "lookup_customer"
    ADD_CASE_NOTE = "add_case_note"
    FLAG_CONCERN = "flag_concern"
    READ_DECISION = "read_decision"
    READ_EXPLANATION = "read_explanation"
    CLAIM_REVIEW = "claim_review"
    REVIEW_DECISION = "review_decision"
    PROPOSE_POLICY_CHANGE = "propose_policy_change"
    APPROVE_POLICY_CHANGE = "approve_policy_change"
    READ_AUDIT = "read_audit"


@dataclass(frozen=True)
class Principal:
    sub: str
    realm: str
    roles: frozenset[str]
    branch_id: Optional[str] = None

    def __post_init__(self) -> None:
        allowed = STAFF_ROLES if self.realm == STAFF_REALM else CUSTOMER_ROLES if self.realm == CUSTOMER_REALM else None
        if allowed is None:
            raise ValueError(f"Unknown realm {self.realm!r}")
        foreign = set(self.roles) - allowed
        if foreign:
            # A customer token can never carry staff roles, and vice versa.
            raise ValueError(f"Roles {sorted(foreign)} are not valid in realm {self.realm}")


@dataclass(frozen=True)
class Resource:
    """The facts about the target that rules may look at. Unused fields stay None."""

    type: str = "application"
    id: Optional[str] = None
    channel: Optional[str] = None  # staff | self
    applicant_sub: Optional[str] = None
    created_by_sub: Optional[str] = None
    branch_id: Optional[str] = None
    status: Optional[str] = None  # latest application status
    consent_recorded: bool = False
    proposed_by: Optional[str] = None  # policy changes
    purpose: Optional[str] = None  # customer lookups


@dataclass(frozen=True)
class AuthzDecision:
    allowed: bool
    rule: str
    reason: str = ""


Condition = Callable[[Principal, Resource], bool]


def _any(p: Principal, r: Resource) -> bool:
    return True


def _own(p: Principal, r: Resource) -> bool:
    return r.applicant_sub is not None and r.applicant_sub == p.sub


def _own_self_channel(p: Principal, r: Resource) -> bool:
    return r.channel == "self" and _own(p, r)


def _own_open(p: Principal, r: Resource) -> bool:
    return _own(p, r) and r.status in {"submitted", MANUAL_REVIEW}


def _same_branch(p: Principal, r: Resource) -> bool:
    return p.branch_id is not None and r.branch_id == p.branch_id


def _staff_channel_same_branch(p: Principal, r: Resource) -> bool:
    return r.channel == "staff" and _same_branch(p, r)


def _handling(p: Principal, r: Resource) -> bool:
    return r.created_by_sub == p.sub


def _handling_with_consent(p: Principal, r: Resource) -> bool:
    return _handling(p, r) and r.consent_recorded


def _in_manual_review(p: Principal, r: Resource) -> bool:
    return r.status == MANUAL_REVIEW


def _review_not_own_submission(p: Principal, r: Resource) -> bool:
    return _in_manual_review(p, r) and r.created_by_sub != p.sub


def _valid_purpose(p: Principal, r: Resource) -> bool:
    return r.purpose in LOOKUP_PURPOSES


def _not_proposer(p: Principal, r: Resource) -> bool:
    return r.proposed_by is not None and r.proposed_by != p.sub


# action -> [(role, rule id, condition)]; a request is allowed when any row matches.
_RULES: dict[Action, list[tuple[str, str, Condition]]] = {
    Action.SUBMIT_APPLICATION: [
        ("applicant", "own", _own_self_channel),
        ("loan_officer", "same_branch", _staff_channel_same_branch),
    ],
    Action.READ_APPLICATION: [
        ("applicant", "own", _own),
        ("loan_officer", "same_branch", _same_branch),
        ("underwriter", "in_manual_review", _in_manual_review),
    ],
    Action.READ_CUSTOMER_PROFILE: [
        ("loan_officer", "handling_application", _handling_with_consent),
        ("underwriter", "in_manual_review", _in_manual_review),
    ],
    # Unmasked citizen ID and phone (ADR-0014): only whoever is working the case, with a reason.
    Action.REVEAL_IDENTITY: [
        ("loan_officer", "handling_application", _handling),
        ("underwriter", "in_manual_review", _in_manual_review),
    ],
    # Extra evidence (payslips) while the file is still open, e.g. when a reviewer asks for it.
    Action.ATTACH_DOCUMENT: [
        ("applicant", "own_open", _own_open),
        ("loan_officer", "same_branch", _same_branch),
    ],
    Action.LOOKUP_CUSTOMER: [
        ("loan_officer", "lookup_purpose", _valid_purpose),
    ],
    Action.ADD_CASE_NOTE: [
        ("loan_officer", "same_branch", _same_branch),
        ("underwriter", "in_manual_review", _in_manual_review),
    ],
    Action.FLAG_CONCERN: [
        ("loan_officer", "same_branch", _same_branch),
        ("underwriter", "in_manual_review", _in_manual_review),
    ],
    Action.READ_DECISION: [
        ("applicant", "own", _own),
        ("loan_officer", "same_branch", _same_branch),
        ("underwriter", "any", _any),
        ("risk_manager", "any", _any),
        ("auditor", "any", _any),
    ],
    Action.READ_EXPLANATION: [
        ("underwriter", "in_manual_review", _in_manual_review),
        ("auditor", "as_recorded", _any),
    ],
    Action.CLAIM_REVIEW: [
        ("underwriter", "separation_of_duties", _review_not_own_submission),
    ],
    Action.REVIEW_DECISION: [
        ("underwriter", "separation_of_duties", _review_not_own_submission),
    ],
    Action.PROPOSE_POLICY_CHANGE: [
        ("risk_manager", "any", _any),
    ],
    Action.APPROVE_POLICY_CHANGE: [
        ("risk_manager", "four_eyes", _not_proposer),
    ],
    Action.READ_AUDIT: [
        ("auditor", "any", _any),
    ],
}


def authorize(principal: Principal, action: Action, resource: Resource) -> AuthzDecision:
    rules = _RULES.get(action, [])
    role_rules = [(rule, cond) for role, rule, cond in rules if role in principal.roles]
    if not role_rules:
        return AuthzDecision(False, "role", f"no role of the caller may {action.value}")
    for rule, cond in role_rules:
        if cond(principal, resource):
            return AuthzDecision(True, rule)
    # Report the first rule the caller's role would need, e.g. "separation_of_duties".
    return AuthzDecision(False, role_rules[0][0], f"{action.value} not permitted by rule {role_rules[0][0]}")


def rules_table() -> dict[str, list[tuple[str, str]]]:
    """The matrix in a printable form (docs, tests)."""
    return {a.value: [(role, rule) for role, rule, _ in rows] for a, rows in _RULES.items()}
