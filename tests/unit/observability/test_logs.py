"""libs/observability writes the log line defined in contracts/telemetry."""

import io
import json
import logging
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from loguru import logger

from observability import SENSITIVE_NAMES, SENSITIVE_SUFFIXES, configure_logging, log_context

CONTRACT = Path(__file__).resolve().parents[3] / "contracts" / "telemetry"
SCHEMA = json.loads((CONTRACT / "log_schema.json").read_text())
VALIDATOR = Draft202012Validator(SCHEMA)


@pytest.fixture
def out():
    """A fresh buffer wired to the library. Restores loguru and the standard library afterwards."""
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    buf = io.StringIO()
    configure_logging("loan-api", "api", level="DEBUG", stream=buf)
    yield buf
    logger.remove()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def lines(buf):
    return [json.loads(x) for x in buf.getvalue().splitlines()]


def only(buf):
    got = lines(buf)
    assert len(got) == 1, got
    return got[0]


def test_schema_is_a_valid_json_schema():
    Draft202012Validator.check_schema(SCHEMA)


def test_plain_line_follows_the_contract(out):
    logger.info("Application accepted", event="application.accepted")
    line = only(out)
    assert list(VALIDATOR.iter_errors(line)) == []
    assert (line["service"], line["component"], line["event"], line["level"]) == (
        "loan-api", "api", "application.accepted", "INFO")
    assert line["timestamp"].endswith("Z")


def test_a_line_without_event_is_named_log(out):
    logger.info("old style")
    assert only(out)["event"] == "log"


def test_an_invalid_event_name_falls_back_and_keeps_the_original(out):
    logger.info("x", event="Feature Ready!")
    line = only(out)
    assert list(VALIDATOR.iter_errors(line)) == []
    assert line["event"] == "log" and line["fields"]["event"] == "Feature Ready!"


@pytest.mark.parametrize("name,expected", [("trace", "DEBUG"), ("success", "INFO"), ("warning", "WARNING"),
                                           ("error", "ERROR"), ("critical", "CRITICAL")])
def test_levels_map_to_the_five_contract_levels(name, expected):
    buf = io.StringIO()
    configure_logging("s", "c", level="TRACE", stream=buf)
    try:
        getattr(logger, name)("m")
        assert only(buf)["level"] == expected
    finally:
        logger.remove()


def test_an_exception_stays_on_one_line_and_validates(out):
    try:
        1 / 0
    except ZeroDivisionError:
        logger.exception("boom", event="job.failed")
    assert out.getvalue().count("\n") == 1
    line = only(out)
    assert list(VALIDATOR.iter_errors(line)) == []
    assert line["error"]["type"] == "ZeroDivisionError"
    assert "Traceback" in line["error"]["stack"]


def test_log_context_adds_business_fields_as_strings(out):
    with log_context(application_id="A-1", sk_id_curr=100001, model_version="v7"):
        logger.info("scored", event="score.done")
    line = only(out)
    assert list(VALIDATOR.iter_errors(line)) == []
    assert (line["application_id"], line["sk_id_curr"], line["model_version"]) == ("A-1", "100001", "v7")
    logger.info("outside")
    assert "application_id" not in lines(out)[-1]


def test_other_fields_go_under_fields(out):
    logger.info("fetched", event="bureau.fetched", rows=12, source="clickhouse")
    line = only(out)
    assert list(VALIDATOR.iter_errors(line)) == []
    assert line["fields"] == {"rows": 12, "source": "clickhouse"}


def test_sensitive_keys_are_redacted_at_any_depth(out):
    logger.info("saved", event="profile.saved", Phone="0901", profile={"full_name": "A B", "city": "HCM", "items": [{"email": "a@b"}]},
                national_id_enc="xx", note="kept")
    f = only(out)["fields"]
    assert f["Phone"] == "[REDACTED]"
    assert f["national_id_enc"] == "[REDACTED]"
    assert f["profile"]["full_name"] == "[REDACTED]"
    assert f["profile"]["items"][0]["email"] == "[REDACTED]"
    assert f["profile"]["city"] == "HCM" and f["note"] == "kept"


def test_redaction_list_matches_the_contract():
    spec = json.loads((CONTRACT / "sensitive_fields.json").read_text())
    assert SENSITIVE_NAMES == frozenset(spec["names"])
    assert SENSITIVE_SUFFIXES == tuple(spec["suffixes"])


def test_standard_library_logging_goes_through_the_same_line(out):
    logging.getLogger("uvicorn.error").warning("Invalid HTTP request received")
    line = only(out)
    assert list(VALIDATOR.iter_errors(line)) == []
    assert line["level"] == "WARNING" and line["message"] == "Invalid HTTP request received"
    assert line["service"] == "loan-api"


def test_trace_id_comes_from_the_active_span(out, monkeypatch):
    pytest.importorskip("opentelemetry.sdk.trace")
    from opentelemetry.sdk.trace import TracerProvider

    monkeypatch.setenv("OTEL_SDK_DISABLED", "false")  # tests/conftest.py turns the SDK off for every test
    tracer = TracerProvider().get_tracer("test")
    with tracer.start_as_current_span("work") as span:
        logger.info("inside", event="work.inside")
        ctx = span.get_span_context()
    line = only(out)
    assert list(VALIDATOR.iter_errors(line)) == []
    assert line["trace_id"] == format(ctx.trace_id, "032x")
    assert line["span_id"] == format(ctx.span_id, "016x")


def test_no_span_means_no_trace_id(out):
    logger.info("alone")
    assert "trace_id" not in only(out)


def test_level_and_format_default_from_the_environment(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    buf = io.StringIO()
    configure_logging("s", "c", stream=buf)
    try:
        logger.info("hidden")
        logger.warning("shown")
        assert [x["message"] for x in lines(buf)] == ["shown"]
    finally:
        logger.remove()


def test_text_format_is_for_people_and_still_one_line_per_event():
    buf = io.StringIO()
    configure_logging("s", "c", fmt="text", stream=buf)
    try:
        with log_context(application_id="A-1"):
            logger.info("hello", event="greet.said")
        text = buf.getvalue()
        assert text.count("\n") == 1
        assert "greet.said" in text and "hello" in text and 'application_id="A-1"' in text
    finally:
        logger.remove()


def test_bad_settings_fail_early():
    with pytest.raises(ValueError, match="LOG_FORMAT"):
        configure_logging("s", "c", fmt="xml", stream=io.StringIO())
    with pytest.raises(ValueError, match="log level"):
        configure_logging("s", "c", level="LOUD", stream=io.StringIO())


def test_calling_configure_twice_does_not_double_the_lines(out):
    buf = io.StringIO()
    configure_logging("loan-api", "api", level="DEBUG", stream=buf)
    logger.info("once")
    assert len(lines(buf)) == 1
