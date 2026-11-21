# Domain model (UML)

The vocabulary and the core objects of the credit decisioning domain. Use these names in code, events and docs. "As built" is what the repository does today; "target" is the design the [handoff packages](../03-handoff/README.md) implement.

## 1. Vocabulary

| Term | Meaning | Where it lives |
|---|---|---|
| **Application** | One loan request, identified by `sk_id_curr` | PostgreSQL `loan_applications` |
| **Applicant data** | Fields the applicant types in (income, credit, dates, flags) | the application row |
| **Feature** | One model input with a name, type, source group and transform | **Feature catalog** (target); today scattered (F-07) |
| **Feature group** | Features produced together: `application`, `external` (bureau), `dwh` (history) | Kafka topic + Feast view per group |
| **Feature catalog** | The single declaration of all features and their properties, versioned | `features.yaml` (target, E2) |
| **Protected attribute** | A feature that must not be a model input (for example gender) | catalog tag `protected` (target) |
| **Readiness** | All three feature groups for an application are in the online store | Redis DB 1 (E3) |
| **Score** | Model output P(default) in [0, 1]. Higher means riskier | decision event |
| **Decision band** | `approve` (p < 0.25), `under_review` (0.25 ≤ p ≤ 0.35), `reject` (p > 0.35) | decision policy config (E5) |
| **Decision** | Band + score + reasons + model and catalog versions, for one application | `application_status_log` (E5) |
| **Reason code** | Machine-readable cause: `score_band`, `features_incomplete`, `feature_data_unavailable`, `rule:<id>` | decision record |
| **Model version** | A registered MLflow version with its `feast_metadata.yaml`, git commit and data snapshot | MLflow |
| **Review queue** | Applications in `under_review` waiting for a human | query on `application_status_log` |

## 2. Class diagram: as built

```mermaid
classDiagram
    direction LR
    class LoanApplication {
        <<entity, PostgreSQL>>
        +sk_id_curr: str
        +birth_date: date
        +amt_income_total: decimal
        +amt_credit: decimal
        +amt_annuity: decimal
        +employment_start_date: date
        +code_gender: str
        +document_id_2..21: str
        +created_at: timestamp
    }
    class ApplicationStatusLog {
        <<table, never written>>
        +sk_id_curr: str
        +status: str
        +created_by: str
        +metadata: json
        +created_at: timestamp
    }
    class FeatureRow {
        <<Kafka topic + Feast view>>
        +sk_id_curr: str
        +group: application|external|dwh
        +values: map
        +ts: float
    }
    class FeatureReadyEvent {
        <<hc.feature_ready>>
        +sk_id_curr: str
        +source: str
        +ts: str
    }
    class ScoringResult {
        <<hc.scoring, no consumer>>
        +sk_id_curr: str
        +probability: float
        +decision: approve|reject|under-review
        +threshold: float
        +model: str
        +version: str
    }
    class ModelVersion {
        <<MLflow>>
        +name: str
        +version: int
        +stage: str
        +feast_metadata: yaml
    }
    LoanApplication "1" --> "0..*" ApplicationStatusLog : intended, not implemented
    LoanApplication "1" --> "3" FeatureRow : CDC fan-out
    FeatureRow "3" --> "1..*" FeatureReadyEvent : can fire repeatedly (F-03)
    FeatureReadyEvent "1" --> "1" ScoringResult : scored by
    ModelVersion "1" --> "0..*" ScoringResult : produces
```

## 3. Class diagram: target

New elements are E2 (catalog), E3 (readiness), E5 (decision) and E6 (governance).

```mermaid
classDiagram
    direction LR
    class FeatureSpec {
        +name: str
        +dtype: str
        +group: FeatureGroup
        +training_column: str
        +nullable: bool
        +protected: bool
        +valid_range: tuple
    }
    class FeatureCatalog {
        <<module, E2>>
        +version: str
        +specs: list~FeatureSpec~
        +model_features() list
        +columns(group) list
        +check_model(feature_names) CatalogCheck
    }
    class ReadinessCoordinator {
        <<module, E3>>
        +register_arrival(sk_id_curr, group) ReadinessStatus
        +expire_incomplete() list
    }
    class ReadinessStatus {
        <<enumeration>>
        PENDING
        READY_FIRST_TIME
        ALREADY_READY
        TIMED_OUT
    }
    class DecisionPolicy {
        <<module, E5>>
        +approve_below: float
        +reject_above: float
        +decide(score) Decision
        +decide_incomplete(reason) Decision
    }
    class Decision {
        <<value object>>
        +band: DecisionBand
        +score: float
        +reasons: list
    }
    class DecisionBand {
        <<enumeration>>
        APPROVE
        UNDER_REVIEW
        REJECT
    }
    class DecisionRecord {
        <<application_status_log row, E5>>
        +event_id: str
        +sk_id_curr: str
        +status: DecisionBand
        +score: float
        +reasons: json
        +model_version: str
        +catalog_version: str
        +created_at: timestamp
    }
    class ModelVersion {
        <<MLflow, E6/E7>>
        +version: int
        +git_commit: str
        +data_snapshot_id: str
        +catalog_version: str
        +dir_gender: float
    }
    FeatureCatalog "1" *-- "many" FeatureSpec
    ReadinessCoordinator ..> ReadinessStatus : returns
    DecisionPolicy ..> Decision : creates
    Decision --> DecisionBand
    DecisionRecord ..> Decision : persists
    ModelVersion ..> FeatureCatalog : validated against
    DecisionRecord --> ModelVersion : produced by
```

## 4. State machine: application lifecycle

The target lifecycle. Today only `Submitted` is persisted; everything after it happens only in Kafka and is never written back (F-04).

```mermaid
stateDiagram-v2
    [*] --> Submitted: POST /applications (row committed)
    Submitted --> FeaturesPending: CDC event fans out to 3 groups
    FeaturesPending --> ReadyForScoring: 3rd group lands (exactly once)
    FeaturesPending --> UnderReview: timeout 300 s<br/>reason features_incomplete
    ReadyForScoring --> Approved: score below 0.25
    ReadyForScoring --> UnderReview: score 0.25 to 0.35
    ReadyForScoring --> Rejected: score above 0.35
    ReadyForScoring --> UnderReview: no online features<br/>reason feature_data_unavailable
    ReadyForScoring --> DeadLettered: 3 delivery retries failed
    DeadLettered --> ReadyForScoring: operator re-drives from DLQ
    UnderReview --> Approved: reviewer approves
    UnderReview --> Rejected: reviewer rejects
    Approved --> [*]
    Rejected --> [*]
```

## 5. State machine: readiness of one application

Owned by the readiness coordinator (E3). Keys live in Redis DB 1.

```mermaid
stateDiagram-v2
    [*] --> Empty
    Empty --> Partial: first group lands (start TTL 300 s)
    Partial --> Partial: another group lands (count < 3) or duplicate
    Partial --> Ready: third distinct group lands<br/>emit feature_ready once (SET dispatched NX)
    Ready --> Ready: any later or duplicate write<br/>no event (ALREADY_READY)
    Partial --> TimedOut: TTL expires<br/>emit feature_timeout
    Ready --> [*]
    TimedOut --> [*]
```

## 6. Where each concept is stored

| Concept | PostgreSQL | Kafka | Redis | MLflow / MinIO |
|---|---|---|---|---|
| Application | `loan_applications` | `hc.applications.public.loan_applications` | | |
| Feature row | | `hc.application_features`, `hc.application_ext`, `hc.application_dwh` | DB 0 (Feast) | |
| Readiness | | `hc.feature_ready`, `hc.feature_timeout` (E3) | DB 1 `feature_coordination:*`, `dispatched:*` | |
| Decision | `application_status_log` (E5) | `hc.scoring` | | |
| Model version | | | | registry + artifacts (`feast_metadata.yaml`, `model_card.md`) |
| Feature catalog | | | | versioned in git; version stamped into model metadata |
