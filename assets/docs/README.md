# Real‑Time Loan Assessment – Docs

This folder contains the minimal, production‑oriented documentation for the system. Use it to align requirements, validate scenarios, and gate releases.

- `system_requirements.md` – scope, KPIs, functional and non‑functional requirements (SLOs), data/versioning, reliability, security, observability, capacity, rollout gates.
- `acceptance_scenarios.md` – end‑to‑end scenarios with clear expected outcomes to validate before go‑live.
- `slos_and_alerts.md` – measurable SLOs/SLIs and the primary Prometheus alert rules we rely on.
- `monitoring/alert-rules.yaml` – drop‑in PrometheusRule for kube‑prometheus‑stack.
- `go_live_checklist.md` – practical, operator‑friendly checklist for launch.

These docs assume the following core stack: API/Decision service, BentoML (or Ray Serve) for inference, Feast (online Redis) for features, Kafka for streaming, ClickHouse for audit/analytics, MLflow for registry, and MinIO for datasets/artifacts.

