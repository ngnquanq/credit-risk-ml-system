# Test Suite

This directory contains the public verification surface for the Home Credit credit-risk platform.

## Layout

- `tests/unit/`: fast tests for domain logic, workflow orchestration, schemas, scoring helpers, Kafka consumers, stream processor behavior, tracing, and infrastructure adapters.
- `tests/integration/`: in-memory API and repository tests that avoid external services.
- `tests/test_load/`: Locust and Kubernetes-oriented load-test harnesses plus investigation notes. These require a deployed stack and are excluded from normal unit/integration runs.

## Recommended Commands

```bash
# Public clone smoke check
PYTHONPATH=application pytest --collect-only -q tests --ignore=tests/test_load

# Unit + integration verification
PYTHONPATH=application pytest tests/unit tests/integration -q

# Load-test helper unit checks only
PYTHONPATH=application pytest tests/test_load/test_prediction_monitor_parsing.py -q
```

The GitHub Actions workflow splits the suite into domain, schema, scoring, infrastructure, consumer, and integration coverage gates.

## Notes

- Integration tests use in-memory or mocked dependencies unless a test explicitly documents otherwise.
- Full E2E load tests require Kubernetes, Kafka, ClickHouse, Feast, and KServe to be running.
- Keep this file aligned with actual paths; avoid hard-coding test counts because they drift quickly.
