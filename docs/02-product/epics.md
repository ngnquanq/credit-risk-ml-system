# Epics

Epics break the [business outcomes](../01-business/business-outcomes.md) into deliverable slices. Each epic lists the outcomes it serves, what already exists in the code, the gaps (with finding IDs from [`architecture/c4/docs/07-findings.md`](../architecture/c4/docs/07-findings.md)), user stories and acceptance criteria. Epics marked **Next** have a full handoff package in [`../03-handoff/`](../03-handoff/README.md).

Status: **Built** = works end to end; **Built, defects** = works but a finding breaks an outcome; **Partial** = some stories built; **Not built**.

## 1. Catalogue

| ID | Epic | Outcomes | Status | Findings | Size | Handoff |
|---|---|---|---|---|---|---|
| E1 | Application intake and document capture | O1, O7 | Built, defects | F-03, F-05 | S | (part of E5, E9) |
| E2 | Feature engineering with training–serving parity | O3, O4 | Built, defects | F-01, F-02, F-07, F-09, F-13 | M | **Next**: [E2](../03-handoff/E2-feature-catalog-and-parity.md) |
| E3 | Exactly-once application readiness | O1, O5 | Built, defects | F-03, F-06, F-15 | M | **Next**: [E3](../03-handoff/E3-exactly-once-readiness.md) |
| E4 | Real-time scoring | O1, O3, O5 | Built, defects | F-10, F-11 | M | (after E5) |
| E5 | Decision delivery and status tracking | O1, O2 | **Not built** | F-04 | M | **Next**: [E5](../03-handoff/E5-decision-delivery.md) |
| E6 | Fair, governed credit model | O3, O4, O6 | Partial | F-07, F-08 | M | **Next**: [E6](../03-handoff/E6-fair-governed-model.md) |
| E7 | Automated, traceable model promotion | O6 | Built, defects | F-12, F-16 | S | (after E6) |
| E8 | Reliable delivery and operations | O5 | Partial | F-06, F-11, F-13, F-14 | L | (after E3) |
| E9 | Security baseline | O7 | Partial | F-17 | S | **Next**: [E9](../03-handoff/E9-security-baseline.md) |
| E10 | Pre-screening business rules | O3, O1 | Not built | n/a | M | (backlog) |

## 2. Traceability: outcomes → epics

```mermaid
flowchart LR
    subgraph Outcomes
        O1[O1 Fast decision]
        O2[O2 Consistent, explainable]
        O3[O3 Risk quality]
        O4[O4 Fair lending]
        O5[O5 Scale without loss]
        O6[O6 Safe model change]
        O7[O7 Data protection]
    end
    subgraph Epics
        E1[E1 Intake]
        E2[E2 Feature parity]
        E3[E3 Exactly-once readiness]
        E4[E4 Real-time scoring]
        E5[E5 Decision delivery]
        E6[E6 Fair, governed model]
        E7[E7 Model promotion]
        E8[E8 Reliable ops]
        E9[E9 Security baseline]
        E10[E10 Pre-screening]
    end
    O1 --> E1 & E3 & E4 & E5 & E10
    O2 --> E5
    O3 --> E2 & E4 & E6 & E10
    O4 --> E2 & E6
    O5 --> E3 & E4 & E8
    O6 --> E6 & E7
    O7 --> E1 & E9
    classDef next fill:#e8f5e9,stroke:#2e7d32,stroke-width:2px;
    classDef notbuilt fill:#fff,stroke:#d62728,stroke-dasharray: 5 5;
    class E2,E3,E5,E6,E9 next
    class E10 notbuilt
```

## 3. Delivery order

Dependencies decide the order. E6 needs E2's catalog to remove `CODE_GENDER` everywhere consistently. E5 needs E3, otherwise duplicate scoring produces duplicate decisions.

```mermaid
flowchart LR
    E9[E9 Security baseline<br/>S] --> E2
    E2[E2 Feature catalog + parity<br/>M] --> E6[E6 Fair, governed model<br/>M]
    E3[E3 Exactly-once readiness<br/>M] --> E5[E5 Decision delivery<br/>M]
    E6 --> E7[E7 Traceable promotion<br/>S]
    E5 --> E4[E4 Scoring perf<br/>M]
    E4 --> E8[E8 Reliable ops<br/>L]
    E5 -.-> E10[E10 Pre-screening<br/>M]
```

Wave 1 (weeks 1–3): E9, E2, E3. Wave 2 (weeks 3–5): E6, E5. Wave 3 (weeks 5–8): E7, E4, E8. E10 after that.

---

## E1. Application intake and document capture

**Goal.** An applicant submits an application and documents once, and the platform has everything it needs to decide.

**Built.** Streamlit form, `POST /api/v1/applications`, presigned upload to MinIO, PostgreSQL storage, CDC to Kafka.

**Gaps.** The API also publishes onto the CDC topic (dual write, F-03), with a new producer per request (F-05). No authentication (E9).

| Story | Acceptance criteria |
|---|---|
| As an applicant I submit my application so that it can be assessed | **Given** a valid payload **when** I POST it **then** I get `201` with `status=submitted`, and exactly one change event appears on `hc.applications.public.loan_applications` |
| As an applicant I upload my ID and payslip | **Given** a supported file type **when** I request a presigned URL and upload **then** the object exists under `{sk_id_curr}/{folder}/` and its `document_id_N` is stored on the application |
| As the platform I publish each application exactly once | **Given** an application is committed **then** only Debezium publishes it; the API has no Kafka producer |

## E2. Feature engineering with training–serving parity

**Goal.** The model sees the same features, computed the same way, in training and in serving.

**Built.** Flink CDC job (applicant features), bureau service + Flink aggregation, DWH service over dbt marts, Feast materialisation.

**Gaps.** `DAYS_EMPLOYED` has the wrong sign at serving (F-01); bureau aggregates are implemented twice (F-02); the model's feature list and the Feast schemas drift apart (F-07); per-applicant ClickHouse lookups are full scans (F-09); Flink has no checkpoints (F-13).

| Story | Acceptance criteria |
|---|---|
| As a data scientist I declare each feature once | **Given** `features.yaml` **then** Feast views, the Flink sink column list, the training feature list and `feast_metadata.yaml` are derived from it, and CI fails if any of them disagree |
| As a risk owner I trust serving values match training values | **Given** a golden set of 50 applicants **when** features are computed by the training path and the serving path **then** every feature matches within 1e-6, and `DAYS_EMPLOYED ≤ 0` or `= 365243` |
| As a platform engineer I get bureau features in bounded time | **Given** 30 RPS **then** the ClickHouse bureau lookup p95 stays under 50 ms (tables ordered by `SK_ID_CURR`) |

## E3. Exactly-once application readiness

**Goal.** Each application is scored exactly once, after all three feature groups are in the online store, or is explicitly flagged when they never arrive.

**Built.** Redis Lua completeness set; `hc.feature_ready` event.

**Gaps.** Readiness fires again on every later write (F-03); an application whose group never arrives disappears silently (F-15); the materialiser loses buffered rows on crash (F-06).

| Story | Acceptance criteria |
|---|---|
| As the scoring pipeline I receive one readiness event per application | **Given** the three groups arrive in any order, any of them duplicated **then** exactly one `feature_ready` event is published |
| As a reviewer I see applications whose data never completed | **Given** a group is missing 300 s after the first one **then** a `feature_timeout` event is published and the application ends in `under_review` with reason `features_incomplete` |

## E4. Real-time scoring

**Goal.** Score a ready application within the O1 budget under O5 load.

**Built.** BentoML service on KServe (serverless), Knative KafkaSource → Sequence → KafkaSink.

**Gaps.** A `FeatureStore` is built per request (F-10); `containerConcurrency: 1` and the KafkaChannel limit throughput (F-11).

| Story | Acceptance criteria |
|---|---|
| As the platform I score at the target rate | **Given** 30 RPS for 10 minutes **then** ≥ 99% of applications get a decision event within 15 s, and `hc.scoring.dlq` stays empty |

## E5. Decision delivery and status tracking

**Goal.** Close the loop: every decision is stored, auditable and visible to the applicant and to reviewers.

**Built.** Nothing past `hc.scoring`. The `application_status_log` table exists but nothing writes to it.

| Story | Acceptance criteria |
|---|---|
| As an applicant I check my application status | **Given** my application was scored **when** I call `GET /api/v1/applications/{id}/status` **then** I see `approved`, `rejected` or `under_review`, the decision time and a reason code |
| As a reviewer I work a queue of borderline cases | **Given** a score in the review band (0.25 ≤ p ≤ 0.35) or incomplete features **then** the application appears in the review queue with score, top reasons and model version |
| As compliance I audit any decision | **Given** a decision **then** the stored record holds score, threshold band, model name and version, feature catalog version and event id; re-delivering the same event does not create a second record |

## E6. Fair, governed credit model

**Goal.** A model that is reproducible, documented, free of protected inputs and checked for disparate impact before it can serve.

**Built.** Three training paths (CLI, notebook, Kubeflow), MLflow registry, calibration metrics.

**Gaps.** `CODE_GENDER` is an input (F-07); the Kubeflow path trains on a different feature set, including the ID (F-08); no model card, threshold rationale or bias audit.

| Story | Acceptance criteria |
|---|---|
| As compliance I know no protected attribute is used | **Given** a candidate model **then** registration fails if any catalog feature tagged `protected` is in its inputs |
| As a risk owner I see fairness evidence per version | **Given** a candidate model **then** its MLflow run has `dir_gender` logged; the run is tagged `fairness_review_required` if it is below 0.80 |
| As a data scientist I get the same model from any training entry point | **Given** the same dataset and config **then** CLI, notebook and Kubeflow produce the same feature list and metrics |
| As a reviewer I read a model card | **Given** a registered version **then** `model_card.md` is logged with data window, metrics by slice, threshold rationale and limitations |

## E7. Automated, traceable model promotion

**Goal.** Promotion is automatic and every serving version is traceable to code and data.

**Gaps.** The build uses a feature branch instead of the training commit (F-16); routing can pick the wrong version and there is no readiness gate (F-12).

| Story | Acceptance criteria |
|---|---|
| As compliance I trace a serving model to its source | **Given** a serving version **then** its MLflow tags give `git_commit` and `data_snapshot_id`, and the Bento was built from that commit |
| As an engineer I never route to an unready or older version | **Given** a promotion **then** the Sequence is patched only after the new InferenceService is `Ready`, and always to the highest version |

## E8. Reliable delivery and operations

**Goal.** No silent loss anywhere and enough telemetry to prove it.

**Gaps.** At-most-once consumers (F-06), single points of failure (F-14), tracing collector not deployed.

| Story | Acceptance criteria |
|---|---|
| As an engineer I never lose an application silently | **Given** a ClickHouse outage **then** messages are retried, then land on a per-stage DLQ with an alert; offsets are committed only after successful produce |
| As an engineer I see end-to-end latency per application | **Given** a submission **then** one trace spans API → consumers → Feast → scoring → decision recorder |

## E9. Security baseline

**Goal.** Applicant data is protected at the edges, and no secrets live in git.

**Built (2026-11-21).** Credential files untracked; Compose-era secrets removed from the tree.

| Story | Acceptance criteria |
|---|---|
| As the platform I only accept authenticated writes | **Given** no or wrong `X-API-Key` **when** calling any `/api/v1/*` route **then** `401`; `/health` stays open |
| As the platform I only allow my own UI cross-origin | **Given** an origin not in `cors_origins` **then** no CORS headers are returned; wildcard origins are rejected at startup |
| As a developer I cannot commit a secret | **Given** a staged file with a credential **then** the gitleaks pre-commit hook blocks the commit |
| As compliance I store no applicant rows in model artifacts | **Given** a registered model **then** its `input_example` is synthetic |

## E10. Pre-screening business rules

**Goal.** Decline clearly ineligible applications before scoring, with an explicit rule reason. Rules and thresholds are in [`business-constraints.md`](../01-business/business-constraints.md); they need confirmation from credit policy before any handoff.
