# ADR-0008: Load Test Pipeline Bottleneck Fixes

## Status

Accepted

## Date

2026-03-21

## Context

The 500-user load test (7,467 inserts, ~25 RPS, 0% failures) revealed two sequential bottlenecks preventing end-to-end predictions from reaching the `hc.scoring` topic:

### Bottleneck 1: Consumer Throughput

The **bureau-consumer** and **feature-consumer** each ran as 1 replica consuming from 4-partition topics, processing messages sequentially with per-message ClickHouse I/O (~13-90ms). This achieved only ~30 and ~25 msg/sec respectively, causing a massive backlog on the CDC topic.

### Bottleneck 2: Feature Coordination TTL

After fixing consumer throughput, the Feast stream processor successfully wrote 18,626 batches to Redis. However, the **3-source Redis coordination never reached 3/3 sources**. The root cause: the 3 source pipelines have vastly different processing speeds:

| Source | Pipeline Path | Processing Lag |
|--------|--------------|---------------|
| `application` | CDC -> Flink (in-memory) -> Feast | ~0 min (real-time) |
| `dwh` | CDC -> Feature consumer (ClickHouse query) -> Feast | ~32 min |
| `external` | CDC -> Bureau consumer (ClickHouse) -> Flink aggregation -> Feast | ~34 min |

The coordination TTL was 300 seconds (5 min). The `application` source's coordination keys expired 27+ minutes before `dwh` and `external` completed, so the coordination count never reached 3/3.

## Decision

### Fix 1: Scale consumers to match partition count

**File:** `platform/data/k8s/query-services/01-query-services.yaml`

- Bureau consumer: `replicas: 1` -> `replicas: 4`
- Feature consumer: `replicas: 1` -> `replicas: 4`
- Resources bumped: CPU `100m/200m` -> `200m/500m`, Memory `128Mi/256Mi` -> `256Mi/512Mi`

Kafka's consumer group protocol assigns 1 partition per replica, giving ~4x throughput with zero code changes.

### Fix 2: Increase coordination TTL

**File:** `platform/ml/k8s/feature-store/feast-configmap.yaml`

- `FEAST_COORDINATION_TTL`: `300` -> `3600` (5 minutes -> 1 hour)

The TTL must exceed the maximum processing spread between the fastest source (Flink/application, real-time) and the slowest source (ClickHouse-dependent bureau/DWH pipelines). The observed spread was ~34 minutes; 1 hour provides adequate margin for burst scenarios.

Redis memory impact is negligible: ~7,500 coordination sets x ~100 bytes = ~750KB.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| Increase TTL to 3600s (chosen) | Simple config change, no code changes, accommodates observed 34-min spread | Coordination keys persist longer in Redis (negligible memory) |
| Remove 3-source coordination entirely | Eliminates the timing problem | Scoring service would need to handle partial features; model accuracy impact unknown |
| Batch ClickHouse queries in consumers | Reduces per-message I/O, narrows processing spread | Requires code changes to bureau/feature consumers, adds complexity |

## Consequences

### Positive

- Pipeline should complete end-to-end predictions under load
- Consumer scaling provides ~4x throughput improvement (~220 msg/sec combined)
- The TTL fix ensures coordination succeeds even with significant source timing spread

### Negative

- 4 replicas per consumer increases cluster resource usage (4x CPU/memory for each consumer deployment)
- Longer TTL means stale coordination keys persist for up to 1 hour in Redis

### Risks

- If the processing spread ever exceeds 1 hour (e.g., ClickHouse degradation), coordination will still fail. Monitor Feast logs for `3/3 sources` during load tests.
- Scoring service uses Knative Eventing, not direct Kafka consumption. Verify Knative trigger is configured for `hc.feature_ready` topic.
