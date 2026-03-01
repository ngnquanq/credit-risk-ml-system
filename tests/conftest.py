"""
Root conftest: isolate every test from real infrastructure.

Patches are applied at session scope BEFORE any application code is imported,
so module-level side effects (tracing setup, Kafka producers, DB engines)
never reach real endpoints.
"""

import os
import pytest


@pytest.fixture(scope="session", autouse=True)
def _set_test_env():
    """Set safe environment variables so Settings() never points at real infra."""
    env_overrides = {
        # Database — will be overridden per-test in integration suite
        "OPS_DB_HOST": "localhost",
        "OPS_DB_PORT": "5432",
        "OPS_DB_USER": "test",
        "OPS_DB_PASSWORD": "test",
        "OPS_DB_NAME": "test_db",
        # Kafka
        "APP_KAFKA_BOOTSTRAP_SERVERS": "localhost:19092",
        "KAFKA_BOOTSTRAP_SERVERS": "localhost:19092",
        # MinIO — constructor doesn't connect, only bucket_exists() does
        "MINIO_ENDPOINT": "localhost:19000",
        # OpenTelemetry — prevent gRPC dial-out
        "OTEL_EXPORTER_OTLP_ENDPOINT": "localhost:14317",
        "OTEL_SDK_DISABLED": "true",
        # Scoring defaults
        "SCORING_MODEL_SOURCE": "local",
        "SCORING_MODEL_PATH": "/tmp/nonexistent.joblib",
    }
    old_values = {}
    for key, value in env_overrides.items():
        old_values[key] = os.environ.get(key)
        os.environ[key] = value

    yield

    # Restore original values
    for key, old_val in old_values.items():
        if old_val is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = old_val


@pytest.fixture(scope="session", autouse=True)
def _patch_tracing(monkeypatch_session):
    """Prevent the OTLP exporter from opening a gRPC channel."""
    from unittest.mock import MagicMock

    mock_exporter = MagicMock()
    monkeypatch_session.setattr(
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
        lambda *a, **kw: mock_exporter,
    )


@pytest.fixture(scope="session")
def monkeypatch_session():
    """Session-scoped monkeypatch (pytest only ships function-scoped)."""
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()
