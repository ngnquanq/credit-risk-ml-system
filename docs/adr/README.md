# Architecture Decision Records

Records of significant architectural decisions. Each ADR captures **why** a decision was made, what alternatives were evaluated, and the trade-offs.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-use-clickhouse-as-data-warehouse.md) | ClickHouse as Data Warehouse | Accepted |
| [0002](0002-event-driven-architecture-with-kafka.md) | Event-Driven Architecture with Kafka | Accepted |
| [0003](0003-feast-as-feature-store.md) | Feast as Feature Store | Accepted |
| [0004](0004-kserve-and-bentoml-for-model-serving.md) | KServe + BentoML for Model Serving | Accepted |
| [0005](0005-migrate-to-kubernetes.md) | Migrate to Kubernetes | Accepted |
| [0006](0006-clean-architecture-for-application-layer.md) | Clean Architecture | Accepted |
| [0007](0007-flink-for-stream-processing.md) | Flink for Stream Processing | Accepted |
| [0008](0008-load-test-pipeline-bottleneck-fixes.md) | Load Test Pipeline Bottleneck Fixes | Accepted |
| [0009](0009-model-training-and-promotion-pipeline.md) | Automated Model Training and Promotion Pipeline | Accepted |

## Creating a New ADR

1. Copy [template.md](template.md) → `XXXX-short-title.md`
2. Fill in all sections
3. Add entry to the index above
