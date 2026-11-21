"""Keep personal data out of audit details (E13 §4.2).

Each action has an allow-list of detail keys. Anything else (names, dates of birth,
phone numbers, document ids, free text that was not asked for) is dropped.
"""

from __future__ import annotations

_COMMON = frozenset({"rule", "reason", "channel", "branch_id", "event_id", "status"})
_ALLOWED: dict[str, frozenset[str]] = {
    "submit_application": frozenset({"channel", "branch_id", "consent"}),
    "lookup_customer": frozenset({"purpose", "result_count", "same_branch"}),
    "decision": frozenset({"band", "score", "reasons", "reason_codes", "bands", "model", "model_version",
                           "feature_set_sha256", "decided_at"}),
    "decision_fallback": frozenset({"reasons", "missing_groups", "error"}),
    "review_decision": frozenset({"from_status", "to_status", "reason_code", "reason"}),
    "claim_review": frozenset(),
    "propose_policy_change": frozenset({"payload"}),
    "approve_policy_change": frozenset({"payload", "proposed_by"}),
    "add_case_note": frozenset({"note_length"}),
    "flag_concern": frozenset({"concern_type"}),
    "model_promoted": frozenset({"model", "model_version", "git_commit", "approved_by"}),
}
_MAX_TEXT = 500


def sanitize(action: str, details: dict | None) -> dict:
    allowed = _COMMON | _ALLOWED.get(action, frozenset())
    clean = {}
    for key, value in (details or {}).items():
        if key not in allowed:
            continue
        if isinstance(value, str) and len(value) > _MAX_TEXT:
            value = value[:_MAX_TEXT]
        clean[key] = value
    return clean
