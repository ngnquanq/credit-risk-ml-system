# ADR 0010: Knative Sequence for Scoring Pipeline Reply Routing

## Status

Accepted

## Context

The scoring pipeline receives feature-ready events from `hc.feature_ready` via a Knative KafkaSource and routes them to a KServe InferenceService for prediction. The prediction results must be published to the `hc.scoring` Kafka topic.

### Problem

Initially, the KafkaSource pointed directly to the InferenceService. While this delivered events for scoring, the HTTP response (containing the prediction) was discarded — Knative KafkaSource has no built-in mechanism to forward HTTP responses to a downstream sink. As a result, `hc.scoring` received 0 messages.

### Constraints

1. The InferenceService name changes with each model version (`credit-risk-v1`, `credit-risk-v2`, etc.)
2. The scoring service returns predictions via HTTP response (CloudEvent-wrapped JSON), not via a Kafka producer
3. The pipeline must be fully reproducible via `make` targets, not ad-hoc kubectl commands

## Decision

Use a **Knative Sequence** to chain the InferenceService step with a KafkaSink reply destination.

### Architecture

```
hc.feature_ready → KafkaSource → Sequence(scoring-pipeline)
                                    ├─ Step: InferenceService (credit-risk-v{N})
                                    └─ Reply: KafkaSink → hc.scoring
```

The Sequence acts as a pipeline: it sends each event to the InferenceService, captures the HTTP response, and forwards it to the KafkaSink which publishes to `hc.scoring`.

### Key Design Decisions

**KafkaChannel over InMemoryChannel**: The Knative Eventing installation (`eventing-core.yaml`) does not include the InMemoryChannel controller. Since we already have Kafka infrastructure, we use KafkaChannel as the Sequence's channel template. This is also more durable than in-memory channels.

**Serving-watcher patches Sequence dynamically**: When the serving-watcher deploys a new model version, it patches the Sequence step to reference the new InferenceService (via `flows.knative.dev/v1` API). The KafkaSource remains static, always pointing to the Sequence.

**Static KafkaSource, dynamic Sequence step**: The KafkaSource is deployed once via `make k8s-scoring-pipeline` and never changes. Only the Sequence step (which InferenceService to call) is updated by the watcher. This separates infrastructure (KafkaSource, KafkaSinks) from model routing (Sequence step).

## Consequences

### Positive

- Predictions flow end-to-end from `hc.feature_ready` to `hc.scoring`
- Model version changes are handled automatically by the serving-watcher
- Pipeline is fully reproducible: `make k8s-scoring-pipeline` deploys all components
- No Kafka producer needed in the scoring service — reply routing is handled by Knative

### Negative

- Adds a Knative Sequence resource to manage
- Requires `kafka-channel-config` ConfigMap to have the correct bootstrap server (patched in `make k8s-knative-kafka`)
- Watcher needs RBAC for `flows.knative.dev/sequences` instead of `sources.knative.dev/kafkasources`

## Related

- [ADR 0002: Event-Driven Architecture with Kafka](0002-event-driven-architecture-with-kafka.md)
- [ADR 0004: KServe and BentoML for Model Serving](0004-kserve-and-bentoml-for-model-serving.md)
- [ADR 0008: Load Test Pipeline Bottleneck Fixes](0008-load-test-pipeline-bottleneck-fixes.md)
