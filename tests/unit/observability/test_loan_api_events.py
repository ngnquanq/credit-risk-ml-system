"""The loan-api events in contracts/telemetry/events.json, emitted by the real code, follow the log schema."""

import io
import json
import logging
from pathlib import Path

import pytest
from fastapi import HTTPException
from jsonschema import Draft202012Validator
from loguru import logger

from audit.writer import InMemoryAuditWriter
from authz import Action, Principal, Resource
from decisions.recorder import DecisionRecorder
from decisions.status_log import InMemoryStatusLogWriter
from entrypoints.api import security
from entrypoints.api.access import require_action
from observability import configure_logging

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "telemetry"
VALIDATOR = Draft202012Validator(json.loads((CONTRACT / "log_schema.json").read_text()))
CATALOG = {e["event"]: e for e in json.loads((CONTRACT / "events.json").read_text())["events"]}


@pytest.fixture
def lines():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    buf = io.StringIO()
    configure_logging("loan-api", "api", level="DEBUG", stream=buf)
    yield lambda: [json.loads(x) for x in buf.getvalue().splitlines()]
    logger.remove()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def one(lines, event):
    got = [x for x in lines() if x["event"] == event]
    assert len(got) == 1, lines()
    line = got[0]
    assert list(VALIDATOR.iter_errors(line)) == [], line
    entry = CATALOG[event]
    assert line["level"] == entry["level"]
    missing = [k for k in entry["requires"] if k not in line]
    assert missing == [], f"{event} lacks {missing}"
    return line


OFFICER = Principal("off-1", "staff", frozenset({"loan_officer"}), "HN01")
OTHER_BRANCH = Principal("off-2", "staff", frozenset({"loan_officer"}), "HN02")
CASE = Resource(type="application", id="app-1", channel="staff", created_by_sub="off-1", branch_id="HN01",
                status="manual_review")


async def test_an_allowed_action_is_logged_next_to_its_audit_row(lines):
    await require_action(OFFICER, Action.READ_APPLICATION, CASE, InMemoryAuditWriter())
    line = one(lines, "authz.access.allowed")
    assert line["status"] == "SUCCESS" and line["action"] == "read_application"
    assert line["actor"] == {"id": "off-1", "type": "staff", "role": "loan_officer"}
    assert line["target"] == {"type": "application", "id": "app-1"}
    assert line["module"] == "entrypoints.api.access"


async def test_a_denied_action_is_logged_as_a_warning_and_still_refused(lines):
    audit = InMemoryAuditWriter()
    with pytest.raises(HTTPException) as refused:
        await require_action(OTHER_BRANCH, Action.REVEAL_IDENTITY, CASE, audit)
    assert refused.value.status_code == 403
    line = one(lines, "authz.access.denied")
    assert line["status"] == "DENIED" and line["reason_code"] == "handling_application"
    assert line["actor"]["id"] == "off-2"
    assert [e["outcome"] for e in audit.events] == ["denied"]


async def test_a_missing_token_is_logged_without_any_token(lines):
    with pytest.raises(HTTPException) as refused:
        await security.get_principal(None)
    assert refused.value.status_code == 401
    line = one(lines, "authn.token.invalid")
    assert line["status"] == "FAILURE" and line["reason_code"] == "missing_bearer_token"


async def test_a_refused_token_logs_why_but_never_the_token(lines, monkeypatch):
    secret = "eyJhbGciOiJSUzI1NiJ9.SECRET-PAYLOAD.SECRET-SIGNATURE"

    class Refusing:
        def verify(self, token):
            raise security.InvalidToken("untrusted issuer")

    monkeypatch.setattr(security, "_verifier", lambda: Refusing())
    with pytest.raises(HTTPException):
        await security.get_principal(f"Bearer {secret}")
    line = one(lines, "authn.token.invalid")
    assert line["reason_code"] == "untrusted_issuer"
    assert "SECRET" not in json.dumps(line)


EVENT = {"event_id": "e-1", "sk_id_curr": 100001, "status": "manual_review", "model_version": "v7", "score": 0.4}


def test_a_recorded_decision_is_logged_once_per_attempt_and_duplicates_say_so(lines):
    recorder = DecisionRecorder(InMemoryStatusLogWriter())
    recorder.handle_decision(EVENT)
    recorder.handle_decision(EVENT)
    first, second = [x for x in lines() if x["event"] == "decisions.recorded"]
    assert list(VALIDATOR.iter_errors(first)) == []
    assert first["fields"]["result"] == "INSERTED" and second["fields"]["result"] == "DUPLICATE"
    assert first["sk_id_curr"] == "100001" and first["model_version"] == "v7"
    assert first["fields"]["outcome"] == "manual_review" and first["status"] == "SUCCESS"
    assert "score" not in json.dumps(first)


def test_a_fallback_decision_is_a_warning_with_its_reason(lines):
    DecisionRecorder(InMemoryStatusLogWriter()).handle_timeout(
        {"event_id": "e-2", "sk_id_curr": 100002, "missing_groups": ["external"]})
    line = one(lines, "decisions.fallback.applied")
    assert line["reason_code"] and line["target"] == {"type": "application", "id": "100002"}
