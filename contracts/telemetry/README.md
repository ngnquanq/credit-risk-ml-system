# Telemetry contract

What every service writes to its logs, so the platform can collect them without knowing the service.
This folder is the specification. The code that follows it is [`libs/observability`](../../libs/observability/README.md).

## Log line

One JSON object per line on stdout. No colour, no line breaks inside a line (a stack trace is one string).
The shape is [`log_schema.json`](log_schema.json).

| Field | Required | Meaning |
|---|---|---|
| `timestamp` | yes | UTC, ISO 8601, ends in `Z` |
| `level` | yes | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `service` | yes | The folder name under `services/` |
| `component` | yes | Process inside the service, for example `api`, `bureau-consumer` |
| `event` | yes | Stable machine name such as `feature_ready.published`. Lines without one carry `log` |
| `module` | yes | Python module that wrote the line, filled in by the library. Filter by part of a service, for example `authz.*` |
| `message` | yes | A sentence for a person. Data goes in fields |
| `trace_id`, `span_id` | when a span is active | Same application, same trace id, in every service |
| `application_id`, `sk_id_curr`, `model_version` | when known | Business context for searching |
| `actor`, `target`, `action`, `status`, `reason_code`, `client_ip` | security events | Who did what to what, and how it ended. `status` is `SUCCESS`, `DENIED` or `FAILURE` |
| `error` | on failures | `type`, `message`, `stack` |
| `fields` | optional | Anything else, with sensitive keys redacted |

## Events a reviewer depends on

[`events.json`](events.json) lists the named events behind audit and alerts, by capability:
`authn.*`, `authz.*`, `identity.*`, `decisions.*`, `audit.*`. The event's prefix says what happened;
`module` says which code wrote it (`authn.token.invalid` comes from `entrypoints.api.security`).
Any event with one of these prefixes must carry `status` (the schema enforces it) and the fields listed in the catalog.
A test fails if the code emits an event in these modules that the catalog does not list, or the catalog lists one the code never emits.

The audit table stays the legal record. These log lines are the signal: they carry the same `trace_id`, so a line leads to the audit row.

## Rules

1. **Never log personal data.** Log the application id, not the person. Keys listed in
   [`sensitive_fields.json`](sensitive_fields.json) are replaced with `[REDACTED]` as a safety net,
   but a sentence such as `f"Hello {name}"` cannot be caught. Not collecting the data is the real control.
2. **Audit is not logging.** The hash-chained audit table stays the record of who did what. A log line never replaces it.
3. **Level and format come from the environment**: `LOG_LEVEL` (default `INFO`) and `LOG_FORMAT` (`json`, default, or `text` for a terminal).
4. **Name events, not sentences.** Alerts and dashboards filter on `event`. Renaming one is a contract change.
5. **One-off scripts may use `print`.** Anything that keeps running writes through the library.

## Changing this contract

Change the schema and `libs/observability` together. The unit tests check that the library's output
validates against `log_schema.json` and that its redaction list equals `sensitive_fields.json`, so one cannot drift from the other.
The platform's log collector (later) reads this same shape.
