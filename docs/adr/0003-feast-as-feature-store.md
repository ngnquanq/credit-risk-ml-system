# ADR-0003: Feast as the Feature Store

## Status

Accepted

## Date

2025-02-01

## Context

ML pipeline requires consistent feature access across training (batch from ClickHouse) and serving (real-time from Redis, <10ms). Without a feature store, training-serving skew is inevitable.

## Decision

Use **Feast** with:
- **Offline store**: ClickHouse (reuse existing DWH)
- **Online store**: Redis (low-latency key-value lookups)
- **Materialization**: Flink streaming jobs write features to Redis
- **Definitions**: centralized in `application/feast_repo/`

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Feast** | Open-source, pluggable backends, Python-native, batch + streaming | Limited built-in streaming materialization |
| **Tecton** | Fully managed, strong streaming | Proprietary, expensive, cloud-only |
| **Custom (Redis + scripts)** | Simple, no new dependency | No versioning, no entity tracking, skew risk |

## Consequences

### Positive

- Single source of truth for feature definitions — eliminates training-serving skew
- ClickHouse offline store avoids adding another data system
- Redis online store provides sub-millisecond retrieval
- `hc.feature_ready` Kafka topic enables event-driven feature signaling

### Negative

- Feast's native streaming materialization is limited — requires custom Flink integration
- Feature schema changes require coordinated updates across Feast and Flink

### Risks

- Redis as SPOF for online serving — mitigated by horizontal scaling
- Feast API changes between versions may require migration effort
