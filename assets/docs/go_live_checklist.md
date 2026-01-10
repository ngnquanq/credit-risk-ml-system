# Go‑Live Checklist (Autonomous Approve/Reject)

## Readiness
- [ ] SLOs and alerts deployed (kube‑prometheus‑stack + alert rules).
- [ ] OpenTelemetry tracing enabled; request_id propagated end‑to‑end.
- [ ] ClickHouse audit table created; anti‑entropy job compares responses vs audits.
- [ ] Security: mTLS between services; secrets in Vault/KMS; MinIO pre‑signed URL TTL ≤ 15 min; AV/DLP on uploads.

## Data & Features
- [ ] Feature freshness dashboards green; max lag ≤ 120 s.
- [ ] Online/offline parity test (< 0.5% mismatch) on recent sample.
- [ ] FeatureService for champion and canary pinned; registry snapshots stored.

## Models
- [ ] Primary and fallback models registered with MLflow tags:
  - feast.project, feast.feature_service, feast.registry_uri, features.schema_hash
  - approve_threshold_primary, approve_threshold_fallback
  - required_features_full, required_features_core
- [ ] Serving deployments configured with pinned FeatureService + registry snapshot.

## Reliability
- [ ] Idempotency keys enforced on decision API; outbox pattern active for Kafka/audit.
- [ ] Kafka DLQs created; replay CLI tested.
- [ ] External adapters: timeouts, retries, circuit breakers, and cache in place.

## Testing
- [ ] Load test 600–800 rps for 60 min: p95 ≤ 300 ms; error < 0.2%.
- [ ] Soak test 4 h at 400–500 rps: no memory/FD leaks.
- [ ] Chaos drills: adapter outage → fallback path; Redis failover; Kafka broker loss.
- [ ] Canary: 5% traffic for ≥ 30 min with guardrails green (latency, error, approval delta, fallback < 2%).

## Operations
- [ ] Runbooks published: High latency, Feature freshness breach, Adapter outage, DLQ growth, Rollback model.
- [ ] Dashboards: Decision API, Features, Model, Kafka, Business, Audit.

## Launch
- [ ] Flip router to 100% champion; enable canary for new model.
- [ ] Announce on‑call schedule; set paging policies.
- [ ] Schedule DR/restore rehearsal within first month.
