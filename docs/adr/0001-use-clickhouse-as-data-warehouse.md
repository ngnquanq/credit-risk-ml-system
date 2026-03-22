# ADR-0001: Use ClickHouse as Analytical Data Warehouse

## Status

Accepted

## Date

2025-01-15

## Context

Platform needs an analytical warehouse for offline analytics, dbt transformations, ad-hoc queries, and Feast offline store. PostgreSQL (OLTP-optimized) is not suitable for heavy analytical workloads at scale.

## Decision

Use **ClickHouse** as the analytical data warehouse.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **ClickHouse**  | Column-oriented (fast aggregations), open-source, self-hosted, low resource footprint, SQL-compatible, SUPER FAST | Smaller community than Postgres-based solutions, less mature CDC story |
| **PostgreSQL (with partitioning)** | Already in stack, familiar | Not optimized for analytical workloads since it is row-oriented, column scans are slow at scale |

## Consequences

### Positive

- Sub-second aggregations over 300K+ records
- ~10x compression ratio
- Native Kafka ingestion via `kafka` table engine
- dbt-clickhouse adapter for SQL transformations
- Self-hosted on K8s — no cloud vendor dependency

### Negative

- ClickHouse-specific SQL dialect and MergeTree engine learning curve
- Read replicas not yet configured

### Risks

- Single-node SPOF — mitigated by planned read replicas
- Schema migrations need more care than Postgres (limited `ALTER COLUMN`)
