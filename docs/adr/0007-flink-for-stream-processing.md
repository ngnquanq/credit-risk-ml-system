# ADR-0007: Apache Flink for Stream Processing

## Status

Accepted

## Date

2025-02-01

## Context

Platform requires real-time stream processing for feature materialization (Kafka → Redis), data enrichment (Kafka → ClickHouse), and producing `hc.feature_ready` events. Needs stateful computation and exactly-once semantics.

## Decision

Use **Apache Flink** for all stream processing, deployed as Kubernetes jobs.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Apache Flink** | True streaming, exactly-once, stateful, rich windowing, Kafka connector | JVM-heavy, steep learning curve |
| **Kafka Streams** | Embedded, lightweight, no separate cluster | Kafka-to-Kafka only, no Python API |
| **Spark Structured Streaming** | Batch+stream unification, familiar | Micro-batch (not true streaming), higher latency |
| **Custom Python consumers** | Simple, no new infra | No state management, no exactly-once, no windowing |

## Consequences

### Positive

- Sub-second event processing latency
- Exactly-once semantics prevent duplicate feature writes
- Stateful processing enables windowed aggregations
- Same engine for both feature materialization and DWH ingestion

### Negative

- JVM resource overhead (~1-2 GB per TaskManager)
- PyFlink has smaller community than Java/Scala Flink

### Risks

- Checkpointing with Kafka + Redis sinks needs careful config for exactly-once
- TaskManager OOM kills lose in-flight state
