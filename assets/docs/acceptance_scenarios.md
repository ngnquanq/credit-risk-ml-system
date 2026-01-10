# Acceptance Scenarios – Autonomous Approve/Reject

Each scenario must return a decision and write an audit row; there is no manual review.

## A. Happy Path
- Given valid inputs and fresh features
- And external adapters respond within timeout
- When a decision request is made
- Then response latency p95 ≤ 300 ms
- And decision ∈ {approve,reject} from `decision_path=primary`
- And an audit row exists within 60 s

## B. External Adapter Timeout
- Given the adapter circuit breaker opens or times out
- When a decision request is made
- Then the fallback model is used (`decision_path=fallback`)
- And latency SLO holds; error rate stays < 0.2%
- And an audit row captures adapter timeout and decision_path

## C. Missing Required Feature/Input
- Given a required field/feature is missing
- When a decision request is made
- Then decision is `reject` with reason `missing_required_data:<field>`
- And `decision_path=rules_only` (or explicit prereq‑reject)

## D. Feast Staleness
- Given a FeatureView is stale beyond SLA
- When a decision request is made
- Then fallback model is used if core features are available
- Else reject with `stale_or_missing_features`
- Alert `featureview_max_lag_seconds > SLA`

## E. Model Server Failure
- Given the primary model server returns 5xx
- When a decision request is made
- Then fallback model is used; if unavailable, rules‑only reject
- Zero 5xx to caller; audit reason captures failure

## F. Kafka Unavailable
- Given Kafka is down
- When decisions are made
- Then responses are still returned and audits persisted locally via outbox
- Outbox retries publish once Kafka is back; no duplicates (idempotency)

## G. Promotion Canary
- Given a model is promoted in MLflow with FeatureService `fs_vN`
- When the controller materializes `fs_vN` and deploys serving
- Then router sends 5% traffic to the new model
- Guardrails: p95 latency ≤ 300 ms, error rate < 0.5%, approval delta within ±3 pp, fallback usage < 2%
- On breach: traffic reverts to champion automatically

## H. Traffic Spike
- Given load reaches 750 rps for 10 min
- When autoscaling occurs
- Then p95 ≤ 300 ms and error < 0.2%

## I. DR/Restore
- Given Redis snapshot and ClickHouse backups
- When restore is executed
- Then system returns to service within RTO ≤ 1 h and no audit gaps beyond RPO ≤ 15 min

