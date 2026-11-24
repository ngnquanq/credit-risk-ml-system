"""loan-api writes the shared log line, and keeps writing it."""

import io
import json
import logging
import re
from pathlib import Path

import pytest
from loguru import logger

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "services" / "loan-api" / "src"


@pytest.fixture
def clean_logging():
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    yield
    logger.remove()
    root.handlers[:] = saved_handlers
    root.setLevel(saved_level)


def test_setup_logging_names_the_service_and_component(clean_logging, monkeypatch):
    from core import log_setup

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    monkeypatch.delenv("LOG_FORMAT", raising=False)
    log_setup.setup_logging("bureau-consumer")
    logger.info("hello", event="test.hello")
    line = json.loads(buf.getvalue())
    assert (line["service"], line["component"], line["event"]) == ("loan-api", "bureau-consumer", "test.hello")


def test_contract_env_wins_over_the_app_settings(clean_logging, monkeypatch):
    from core import log_setup

    buf = io.StringIO()
    monkeypatch.setattr("sys.stdout", buf)
    monkeypatch.setenv("LOG_LEVEL", "ERROR")
    log_setup.setup_logging("api")
    logger.warning("hidden")
    logger.error("shown")
    assert [json.loads(x)["message"] for x in buf.getvalue().splitlines()] == ["shown"]


def test_both_loan_api_images_ship_the_library():
    for dockerfile in ("services/loan-api/Dockerfile", "services/loan-api/src/entrypoints/Dockerfile"):
        text = (ROOT / dockerfile).read_text()
        assert "COPY libs/observability /app/observability" in text, dockerfile


# One-off or machine-format output that is allowed to print. Everything else logs.
PRINT_ALLOWED = {"audit/verify_job.py"}  # writes Prometheus text for a probe


def test_loan_api_code_does_not_print_or_use_the_standard_logging_module():
    offenders = []
    for path in SRC.rglob("*.py"):
        rel = path.relative_to(SRC).as_posix()
        for n, text in enumerate(path.read_text().splitlines(), 1):
            if re.match(r"\s*print\(", text) and rel not in PRINT_ALLOWED:
                offenders.append(f"{rel}:{n} print")
            if re.match(r"\s*(import logging\b|from logging\b)", text):
                offenders.append(f"{rel}:{n} stdlib logging")
    assert offenders == [], "Use `from loguru import logger` (see libs/observability):\n" + "\n".join(offenders)
