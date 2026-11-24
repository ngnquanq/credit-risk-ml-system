# observability

Shared logging for every service. It writes the log line defined in [`contracts/telemetry`](../../contracts/telemetry/README.md),
so the platform can collect logs from any service the same way.

This is a library, not a service: it has no image and no manifest. Services import it. It imports no service
(an import-linter contract enforces this). Keep it small. It holds only what cannot be done outside the process:
the shape of a log line, business context on it, the trace id, and redaction of sensitive keys.
Models, business rules and Kafka or database clients do not belong here.

## Use

```python
from loguru import logger
from observability import configure_logging, log_context

configure_logging(service="loan-api", component="api")   # once, at start-up

with log_context(application_id="A-123", sk_id_curr=100001):
    logger.info("Features ready", event="feature_ready.published", rows=3)
```

- `configure_logging` also routes the standard library's loggers (uvicorn, kafka, mlflow) through the same line.
- `LOG_LEVEL` (default `INFO`) and `LOG_FORMAT` (`json` default, or `text` for a terminal) come from the environment.
- `trace_id` and `span_id` are added when an OpenTelemetry span is active. The library works without OpenTelemetry installed.
- Name important lines with `event=` (lower case, dots). A line without one carries `event: "log"`.
- Keys such as `phone`, `full_name`, `token` or anything ending in `_enc` are replaced with `[REDACTED]` inside `fields`.
  This is a safety net. Write the application id, never the person, in the message.
  An exception's message is also logged, so do not raise errors that contain personal data.

## Tests

`tests/unit/observability/` checks the output against `log_schema.json` and keeps the redaction list equal to
`sensitive_fields.json`. Change the contract and this library together.

## Not yet done

Trace-context propagation helpers and metric helpers are not here yet. Services still configure logging their own way.
They move to this library one at a time, and each image must install it (copy `libs/observability` and add it to the Python path).
