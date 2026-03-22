# ADR-0005: Migrate from Docker Compose to Kubernetes

## Status

Accepted

## Date

2025-01-28

## Context

Platform originally ran on Docker Compose (10+ compose files). Hit limitations: no auto-scaling, no self-healing, no RBAC, no CRD support. KServe, Knative, and Kubeflow all require Kubernetes-native APIs.

## Decision

Migrate to **Kubernetes** (Minikube for local dev). Docker Compose files retained as reference.

Phased migration:
1. Core infra (Postgres, Kafka, ClickHouse, MinIO) → K8s StatefulSets
2. ML platform (MLflow, KServe, Kubeflow, Feast) → K8s with Helm
3. Observability (Prometheus, Grafana, ECK) → K8s
4. Networking → Kourier + ClusterIP services

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Kubernetes (Minikube)** | Industry standard, CRDs, auto-scaling, self-healing, RBAC | Heavy resources (~32 GB RAM), complex debugging |
| **Docker Compose (keep)** | Simple, familiar, lightweight | No CRDs, no auto-scaling, no RBAC, scaling ceiling |
| **Docker Swarm** | Simpler than K8s, Docker-native | No CRDs, essentially deprecated |

## Consequences

### Positive

- KServe, Knative, Kubeflow, Feast work natively with CRDs
- Self-healing: failed pods restart automatically
- Namespace isolation between data, ML, and ops platforms
- `Makefile` targets provide one-command deployment
- Clear path to managed K8s (EKS/GKE) for production

### Negative

- Minikube requires 32 GB+ RAM for full stack
- Docker Compose files retained but may drift out of sync

### Risks

- Minikube IP changes after restart break service connectivity — mitigated by `make k8s-up`
- Resource contention on single-node can cause OOM kills
