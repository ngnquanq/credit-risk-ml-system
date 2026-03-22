# ADR-0002: Event-Driven Architecture with Apache Kafka

## Status

Accepted

## Date

2025-01-15

## Context

The platform processes loan applications through multiple stages: ingestion, feature enrichment, scoring, and decision output. Synchronous REST calls cause tight coupling, cascading failures, and no replay capability.

## Decision

Use **Apache Kafka** as the central event streaming platform. Debezium captures CDC from PostgreSQL into Kafka topics.

Key topics:
- `hc.public.loan_applications` — CDC from PostgreSQL
- `hc.feature_ready` — features materialized in online store
- `hc.scoring.requests` / `hc.scoring.results` — model inference I/O
- `hc.enriched_applications` — enriched data to ClickHouse

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Apache Kafka** | High throughput, durable log, replay, mature CDC ecosystem (Debezium), partitioning | Operational complexity |
| **RabbitMQ** | Simple, low latency, flexible routing | No log replay, limited throughput at scale |
| **Direct REST** | Simple, familiar | Tight coupling, no buffering, cascading failures |

## Consequences

### Positive

- Producers and consumers evolve independently
- Event replay enables reprocessing after bug fixes or model updates
- Debezium captures every DB change without modifying application code
- Knative Eventing integration provides Kafka → KServe bridge

### Negative

- Debugging event flows is harder than tracing synchronous calls
- No Schema Registry yet — schema evolution requires manual coordination

### Risks

- Kafka broker failure halts the pipeline — mitigated by replication factor ≥ 2
- Consumer lag during traffic spikes delays scoring SLA — monitored via Prometheus
