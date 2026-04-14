# ADR-0004: KServe + BentoML for Model Serving

## Status

Accepted

## Date

2025-02-01

## Context

Need to serve XGBoost models with sub-second latency, auto-scaling (scale-to-zero), blue-green deployments, and Kafka integration for async scoring.

## Decision

Dual-layer serving:
1. **BentoML** — packages model + preprocessing into portable Bento bundles stored in MinIO
2. **KServe** — deploys Bento bundles as `InferenceService` with Knative auto-scaling

Automated pipeline: MLflow watcher detects promotion → builds Bento → serving watcher deploys KServe InferenceService.

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **KServe + BentoML** | Auto-scaling, portable bundles, blue-green, Kafka via Knative | Complex setup (Knative + Kourier + KServe) |
| **BentoML standalone** | Simpler deployment | No auto-scaling, no canary, manual K8s manifests |
| **Seldon Core** | Feature-rich, multi-framework | Heavier resources, complex CRDs, license changes |
| **FastAPI wrapper** | Simple, full control | No auto-scaling, no standard model format |

## Consequences

### Positive

- Scale-to-zero reduces resource usage during idle periods
- Bento bundles are self-contained (model + preprocessing + deps)
- Automated pipeline eliminates manual deployment
- Knative Eventing enables Kafka → model scoring flow

### Negative

- Knative + KServe control plane is resource-heavy (~2 GB RAM overhead)
- Cold-start latency ~5-10s when scaling from zero

### Risks

- Knative webhook timeouts can block all pod creation cluster-wide
- KServe version upgrades may break InferenceService API
