# Runbooks (E15)

One page per failure mode in [E15 §5](../03-handoff/E15-resilience-failover.md#5-data-contracts). Each lists how you notice, what the system already does on its own, what you do, and how you confirm recovery. The rule behind all of them: while something is broken, applications go to manual review, never to an automatic approval.

| Runbook | Trigger |
|---|---|
| [Scoring down](scoring-down.md) | `decisions_total{reason="scoring_unavailable"}` rising, DLQ growing |
| [Kafka broker lost](kafka-broker-lost.md) | Under-replicated partitions > 0 |
| [Database failover](db-failover.md) | CloudNativePG primary changed, API 5xx spike |
| [Keycloak down](keycloak-down.md) | Sign-in errors, `/health/ready` failing |
| [Re-drive a dead-letter queue](dlq-redrive.md) | `hc.decisions.dlq` or `hc.scoring.dlq` not empty after an incident |

Drills: `make chaos-drill TARGET=…` and `make restore-drill` write reports to `reports/drills/`, which the [release checklist](../release/checklist.md) links.
