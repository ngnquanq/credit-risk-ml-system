# SLOs, SLIs, and Alerts

## Service‑Level Objectives
- Availability (decision API): 99.9% monthly.
- Latency (end‑to‑end): p50 ≤ 120 ms, p95 ≤ 300 ms.
- Audit completeness: 100% of responses have matching audit rows within 60 s.
- Feature freshness: 99% of online reads ≤ 120 s lag.
- Fallback usage: < 1% normal; page at ≥ 5% over 10 min.

## Core SLIs (PromQL sketches)
- Error rate:
  - `sum(rate(http_requests_total{job="api",status=~"5.."}[5m])) / sum(rate(http_requests_total{job="api"}[5m]))`
- Decision p95 latency:
  - `histogram_quantile(0.95, sum by (le)(rate(decision_latency_seconds_bucket[5m])))`
- Audit gap (should be ~0):
  - `sum(rate(decision_responses_total[5m])) - sum(rate(audit_written_total[5m]))`
- Feature freshness breach:
  - `max(feast_featureview_max_lag_seconds) > 120`
- Fallback ratio:
  - `sum(rate(decision_path_total{path="fallback"}[10m])) / sum(rate(decision_responses_total[10m]))`
- Kafka consumer lag:
  - `max(kafka_consumergroup_lag{consumergroup=~".+"})`

## Alerts (primary)
- `APIHighLatencyP95` – p95 > 300 ms for 10m.
- `APIHighErrorRate` – error rate > 0.2% for 5m.
- `AuditGapDetected` – audit gap > 5/min for 5m.
- `FeatureFreshnessBreach` – any FeatureView lag > 120 s for 5m.
- `FallbackSpike` – fallback ratio ≥ 5% for 10m.
- `KafkaLagHigh` – lag above threshold for 10m.
- `RedisEvictions` – evictions > 0 or hit ratio < 0.9 for 10m.

See `monitoring/alert-rules.yaml` for a ready‑to‑apply PrometheusRule.
