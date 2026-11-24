# Architecture Decision Records

Records of significant architectural decisions. Each ADR captures **why** a decision was made, what alternatives were evaluated, and the trade-offs.

## Where an ADR sits

An ADR is not a step in the chain from outcome to story. It is the record of a decision taken while an epic is being shaped.

```mermaid
flowchart LR
    O["Outcome<br/>why"] --> E["Epic<br/>what"]
    E --> F["Features and stories<br/>how we know it works"]
    E -. "needs a significant choice" .-> A["ADR<br/>why we built it this way"]
    A -. "constrains" .-> F
    A -. "creates follow-up work" .-> E
```

- It **serves** outcomes and epics: every ADR names them in its "Serves" section, and an epic lists its ADRs.
- It is written for an *architecturally significant* decision: one that affects a quality attribute (security, scalability, reliability, modifiability) or the structure of the system, and is costly to change. Class design and library versions are not.
- It is short (one or two pages) and **not edited once accepted**. A changed decision is a new ADR that supersedes the old one, and each names the other.
- It does not hold tasks. Work that follows from its consequences goes to the epic (as a feature, or as an enabler if it only prepares the ground).
- Its "Compliance" section names the test or check that would fail if the decision stopped being followed.

Sections follow Richards and Ford (*Fundamentals of Software Architecture*, the chapter on architecture decisions, from Michael Nygard's 2011 format). "Serves" and the security additions (threats in the context, residual risk in the consequences) are this repository's own, drawn from the same books' guidance on tracing decisions and on security architecture.

## Index

| ADR | Title | Status |
|-----|-------|--------|
| [0001](0001-use-clickhouse-as-data-warehouse.md) | ClickHouse as Data Warehouse | Accepted |
| [0002](0002-event-driven-architecture-with-kafka.md) | Event-Driven Architecture with Kafka | Accepted |
| [0003](0003-feast-as-feature-store.md) | Feast as Feature Store | Accepted |
| [0004](0004-kserve-and-bentoml-for-model-serving.md) | KServe + BentoML for Model Serving | Accepted |
| [0005](0005-migrate-to-kubernetes.md) | Migrate to Kubernetes | Accepted |
| 0006 | Clean Architecture (never written; see [history](../history/clean-architecture-migration-guide.md)) | Accepted |
| [0007](0007-flink-for-stream-processing.md) | Flink for Stream Processing | Accepted |
| [0008](0008-load-test-pipeline-bottleneck-fixes.md) | Load Test Pipeline Bottleneck Fixes | Accepted |
| [0009](0009-model-training-and-promotion-pipeline.md) | Automated Model Training and Promotion Pipeline | Accepted |
| [0010](0010-knative-sequence-scoring-pipeline.md) | Knative Sequence for Scoring Pipeline Reply Routing | Accepted |
| [0011](0011-monorepo-layout-for-portals-contracts-and-environments.md) | Monorepo layout for portals, contracts and environments | Accepted |
| [0012](0012-keycloak-realms-and-bff-portals.md) | Keycloak with two realms, and backend-for-frontend portals | Accepted |
| [0013](0013-role-based-data-and-explanation-visibility.md) | Role-based visibility of customer data and explanations; officers do not decide | Accepted |
| [0014](0014-applicant-personal-data-and-opaque-ids.md) | Applicant personal data is kept apart and encrypted; URLs carry opaque ids only | Accepted |
| [0015](0015-services-layout-high-cohesion-low-coupling.md) | One folder per deployable service; services share only contracts | Accepted |

## By epic (pilot)

The identity and access flow is the first slice written this way. The other epics list their decisions as they are revisited.

| Epic | Decisions |
|---|---|
| [E11 Identity and access](../02-product/epics.md#e11-identity-and-access) | [0012](0012-keycloak-realms-and-bff-portals.md) Keycloak, two realms, portals as backends-for-frontend · [0013](0013-role-based-data-and-explanation-visibility.md) who sees which data · [0014](0014-applicant-personal-data-and-opaque-ids.md) personal data and opaque ids |

## Creating a New ADR

1. Copy [template.md](template.md) → `XXXX-short-title.md`
2. Fill in all sections, including **Serves** (outcomes, epics) and **Compliance** (the check that proves it is followed)
3. Add the entry to the index above and to the epic's "Decisions" row
