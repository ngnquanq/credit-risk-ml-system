# System Requirements – Real‑Time Loan Assessment (Autonomous)

This application makes fully automated loan decisions: outcomes are only `approve` or `reject`.

## Scope & Personas
- Personas: Applicant, Analyst, Data Scientist, SRE/Platform.
- MVP scope: online application + document upload, real‑time decision, full audit + reasons, portfolio monitoring, autonomous rollouts of new models.

## Business KPIs
- Approval rate, expected loss (EL), charge‑off/bad rate (30/60/90 DPD), model calibration (Brier/KS), time‑to‑decision, cost per RPS.

## Functional Requirements
- Submit application: idempotent request; docs via pre‑signed MinIO URLs.
- Decisioning (binary):
  1) Enforce hard blocks (fraud/blacklist/velocity) → reject.
  2) Validate required inputs/features; if missing → reject with `missing_required_data:<field>`.
  3) Fetch online features from Feast/Redis (pinned FeatureService + registry snapshot).
  4) External data adapters with strict timeouts/circuit breakers; if unavailable → fallback model path (see below).
  5) Score with primary model and apply deterministic rules/thresholds → approve or reject.
- Fallback policy (no manual review): if prerequisites for the primary model aren’t met (e.g., stale/missing features or adapter timeout), use a “lite” fallback model that depends only on core local features. If even core requirements fail → deterministic rules‑only reject.
- Auditing: immutable record to ClickHouse for every response, including inputs (redacted), features, model/feature versions, explanations, decision, and `decision_path={primary|fallback|rules_only}`.
- Model ops: MLflow‑driven promotion triggers Feast materialization, deploys a new serving pod pinned to the model’s FeatureService/registry snapshot, and rolls out via shadow/canary with automatic rollback.

## Non‑Functional Requirements (SLOs)
- Availability: decision API 99.9% per month.
- Latency (end‑to‑end): p50 ≤ 120 ms, p95 ≤ 300 ms.
- Throughput: steady 500 rps; burst 750 rps for 10 min within SLOs.
- Feature freshness: 99% of online reads ≤ 2 minutes lag.
- Audit completeness: 100% of responses have a matching audit row within 60 s.
- Fallback usage: < 1% normal; alert at ≥ 5% over 10 min.
- DR: RTO ≤ 1 h, RPO ≤ 15 min for decision data.

## Data & Versioning
- Each model version must pin, via MLflow tags:
  - `feast.project`, `feast.feature_service` (e.g., `credit_risk_fs_v3`).
  - `feast.registry_uri` (immutable snapshot URI) and `features.schema_hash`.
  - `approve_threshold_primary`, `approve_threshold_fallback`, and lists of `required_features_full` / `required_features_core`.
- FeatureService definitions are immutable; create `*_vN` for changes.
- Online/offline parity tests on recent requests; mismatch < 0.5%.

## Reliability
- External adapters: 200–400 ms timeouts, retries with jitter, circuit breakers, short‑TTL cache. When unavailable → fallback model path automatically.
- Kafka hygiene: Schema Registry, DLQs, idempotent producers/consumers, replay tooling.
- Idempotency: request key on decision API; outbox pattern for Kafka/Audit.

## Security & Compliance
- mTLS in cluster; secrets via Vault/KMS. PII encrypted at rest and redacted in logs.
- MinIO pre‑signed URLs (TTL ≤ 15 min), AV/DLP scan on upload.
- Explanations/adverse‑action reasons are deterministic and stored per decision.

## Observability
- OpenTelemetry tracing across API → features → adapters → model → audit; propagate `request_id`.
- Metrics (Prometheus): decision latency/errors/outcomes, `decision_path` counts, Feast fetch latency/misses/freshness, inference latency/errors, Kafka lag/DLQ, audit write latency/errors.

## Capacity Starting Points
- Decision pods: 6–8 (2 vCPU, 3–4 GiB), HPA to 15–20; PDBs enabled.
- Redis: 3 masters + 3 replicas, AOF `everysec`.
- Kafka: ≥ 12 partitions for hot topics; RF=3.
- ClickHouse: batch insert 50k–200k rows.

## Rollout Gates (Go/No‑Go)
- Load 600–800 rps for 60 min with SLOs green.
- Soak 4 h at 400–500 rps; no leaks.
- Chaos drills (adapter outage, Redis failover, Kafka broker loss) pass.
- Canary guardrails pass: latency/error, approval delta (±3 pp), fallback usage < 2%.
- DR drill successful.

