# Domain model (UML)

The vocabulary and the core objects of the credit decisioning domain. Use these names in code, events and docs. "As built" is what the repository does today; "target" is the design the [handoff packages](../03-handoff/README.md) implement.

## 1. Vocabulary

| Term | Meaning | Where it lives |
|---|---|---|
| **Application** | One loan request. Internally keyed by `sk_id_curr` (the customer key that joins all data); outside the API only by its opaque `public_id` (ADR-0014) | PostgreSQL `loan_applications` |
| **Applicant identity** | Name, citizen ID and phone of one customer, encrypted per field; found by the keyed hash of the citizen ID; shown masked, revealed only with an audited reason | PostgreSQL `applicant_identity`, not replicated (ADR-0014) |
| **Document** | An uploaded ID card side or payslip, keyed by the uploader's HMAC tag; expires after 90 days | MinIO `loan-documents`; id in `loan_applications.document_id_N` |
| **Applicant data** | Fields the applicant types in (income, credit, dates, flags) | the application row |
| **Feature** | One model input with a name, type, source group and transform | **Feature catalog** (target); today scattered (F-07) |
| **Feature group** | Features produced together: `application`, `external` (bureau), `dwh` (history) | Kafka topic + Feast view per group |
| **Feature definition** | What one feature means, its type, producer, valid range and sentinel | `contracts/feature_catalog/definitions/*.yaml` (target, E2) |
| **Feature set** | An immutable, ordered list of definitions that one model uses, with a SHA-256 digest | `contracts/feature_catalog/sets/<version>.json` (`legacy-v1` built) |
| **Protected attribute** | A feature that must not be a model input (for example gender) | catalog tag `protected` (target) |
| **Readiness** | All three feature groups for an application are in the online store | Redis DB 1 (E3) |
| **Score** | Model output P(default) in [0, 1]. Higher means riskier | decision event |
| **Decision band** | `approve` (p < 0.25), `under_review` (0.25 ≤ p ≤ 0.35), `reject` (p > 0.35) | decision policy config (E5) |
| **Decision** | Band + score + reasons + model version and feature-set digest, for one application | `application_status_log` (E5) |
| **Decision reason** | Why the system routed an application: `score_band`, `features_incomplete`, `feature_data_unavailable`, `rule:<id>` | decision record |
| **Model reason code** | A feature-level cause of a high score, from SHAP attributions, mapped through the catalog (for example `EXT_SCORE_LOW`) | decision record `reason_codes` (E14) |
| **Explanation** | The ordered model reason codes plus their contributions for one decision | decision record (E14) |
| **Model version** | A registered MLflow version with its `feast_metadata.yaml`, git commit and data snapshot | MLflow |
| **Review queue** | Applications in `under_review` waiting for a human | query on `application_status_log` |
| **Channel** | How an application arrived: `staff` (entered by a loan officer) or `self` (applicant online) | `loan_applications.channel` (E1/E11) |
| **Branch** | The lender branch or point of sale a staff member and a staff-channel application belong to | Keycloak user attribute `branch_id`; `loan_applications.branch_id` |
| **Principal** | The verified caller of one request: subject, realm, roles, branch | built from the JWT by the API (E11) |
| **Realm** | Keycloak identity domain: `staff` or `customers`. A principal belongs to exactly one | Keycloak |
| **Role** | `applicant`, `loan_officer`, `underwriter`, `risk_manager`, `auditor`, `admin` | Keycloak realm roles |
| **Permission** | An action on a resource type, granted to roles under conditions (own, same branch, not own submission) | policy table in `application/authz/policy.py` (E11) |
| **Override** | A reviewer's decision on an `under_review` application, with a mandatory reason | decision record + audit event (E5, E13) |
| **Policy change** | A proposed new threshold or review band; active only after a second risk manager approves | `policy_change` table (E11) |
| **Audit event** | One immutable record of who did what to which resource, when, and the outcome | `audit_event` table, append-only, hash-chained (E13) |

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
        +definitions: list~FeatureSpec~
        +check_set(feature_set) CatalogCheck
    }
    class FeatureSet {
        <<built: feature_preprocessing.py>>
        +version: str
        +digest: str
        +columns() list
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
        +feature_set_sha256: str
        +created_at: timestamp
    }
    class ModelVersion {
        <<MLflow, E6/E7>>
        +version: int
        +git_commit: str
        +data_snapshot_id: str
        +feature_set_sha256: str
        +dir_gender: float
    }
    FeatureCatalog "1" *-- "many" FeatureSpec
    FeatureSet ..> FeatureSpec : references in order
    ReadinessCoordinator ..> ReadinessStatus : returns
    DecisionPolicy ..> Decision : creates
    Decision --> DecisionBand
    DecisionRecord ..> Decision : persists
    ModelVersion --> FeatureSet : trained on (version, digest)
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
| Feature catalog | | | | versioned in git; set version and digest stamped into model metadata |
| Identity, role, branch | Keycloak database (separate instance) | | | |
| Application ownership | `loan_applications.channel`, `created_by_sub`, `applicant_sub`, `branch_id` (E11) | CDC event carries them | | |
| Applicant identity | `applicant_identity` (encrypted, ADR-0014) | **never** (not in the CDC publication) | | |
| Documents | document ids on the application row | ids only | | `loan-documents` bucket, 90-day expiry |
| Estimator draft (amount, term) | | | portal Redis `draft:*`, 30 minutes | |
| Explanation | `application_status_log.metadata.reason_codes` (E14) | `hc.scoring` payload | | |
| Audit event | `audit_event` (append-only, E13) | | | searchable copy in Elasticsearch (ECK) |
| Policy change | `policy_change` (E11) | | | |

## 7. Class diagram: identity, access and audit (target)

```mermaid
classDiagram
    direction LR
    class Principal {
        <<value object, per request, E11>>
        +sub: str
        +realm: staff or customers
        +roles: set~Role~
        +branch_id: str or None
    }
    class Role {
        <<enum>>
        applicant
        loan_officer
        underwriter
        risk_manager
        auditor
        admin
    }
    class Action {
        <<enum>>
        submit_application
        read_application
        read_decision
        read_explanation
        read_customer_profile
        lookup_customer
        add_case_note
        flag_concern
        review_decision
        propose_policy_change
        approve_policy_change
        read_audit
    }
    class Resource {
        <<value object>>
        +type: application or decision or policy or audit
        +id: str
        +channel: staff or self
        +owner_sub: str or None
        +created_by_sub: str or None
        +branch_id: str or None
    }
    class Policy {
        <<module: application/authz/policy.py>>
        +authorize(principal, action, resource) AuthzDecision
    }
    class AuthzDecision {
        <<value object>>
        +allowed: bool
        +rule: str
        +reason: str
    }
    class AuditEvent {
        <<append-only row, E13>>
        +id: bigint
        +occurred_at: timestamp
        +actor_sub: str
        +actor_realm: str
        +actor_roles: list
        +action: Action
        +resource_type: str
        +resource_id: str
        +outcome: allowed or denied or error
        +trace_id: str
        +details: json, no raw PII
        +prev_hash: bytes
        +hash: bytes
    }
    class Explanation {
        <<value object, E14>>
        +base_value: float
        +contributions: dict
        +reason_codes: list~str~
    }
    class Override {
        <<E5 + E13>>
        +reviewer_sub: str
        +from_band: DecisionBand
        +to_status: approved or rejected
        +reason: str
    }
    class PolicyChange {
        <<E11>>
        +proposed_by: str
        +approved_by: str or None
        +review_band: tuple
        +state: proposed or active or rejected
    }
    Principal --> Role
    Policy ..> Principal : reads
    Policy ..> Resource : reads
    Policy ..> AuthzDecision : returns
    AuditEvent ..> AuthzDecision : records outcome of
    Decision --> Explanation : carries
    Override --> Decision : resolves under_review
    PolicyChange ..> DecisionPolicy : configures once approved
```

`Policy.authorize` is the only place that grants access. Routes call it and audit the result; they never check roles themselves. Its rules are the [permission matrix in E11](../03-handoff/E11-identity-access.md#5-data-contracts).

## 8. State machine: manual review of one application

```mermaid
stateDiagram-v2
    [*] --> Queued: decision band under_review<br/>or features timeout or scoring unavailable
    Queued --> Claimed: underwriter claims (not the submitter)
    Claimed --> Queued: released, or claim older than 30 min
    Claimed --> Approved: approve with reason
    Claimed --> Rejected: reject with reason
    Approved --> [*]
    Rejected --> [*]
```

Every transition writes an audit event. Claiming fails with `separation_of_duties` when the underwriter's `sub` equals the application's `created_by_sub`.

## 9. State machine: decision policy change (four eyes)

```mermaid
stateDiagram-v2
    [*] --> Proposed: risk manager proposes band or threshold
    Proposed --> Active: a different risk manager approves
    Proposed --> Rejected: a different risk manager rejects
    Proposed --> Expired: no decision within 7 days
    Active --> Superseded: a later change becomes active
    Rejected --> [*]
    Expired --> [*]
    Superseded --> [*]
```
