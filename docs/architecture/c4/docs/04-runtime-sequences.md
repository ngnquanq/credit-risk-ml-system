# 4. Runtime sequences

Each sequence below matches a Structurizr dynamic view (`D1` … `D8`). The dynamic views show *which* elements take part. The Mermaid diagrams add the detail a dynamic view cannot show: payloads, consumer groups, retries, alternatives and failure branches. Steps marked ⚠ link to a finding in [07-findings.md](07-findings.md).

| # | Flow | Dynamic view | Trigger |
|---|---|---|---|
| S1 | Submit an application | `D1-Submit-Application`, `D1a-API-Submission` | Applicant presses Submit |
| S2 | CDC fan-out and feature engineering | `D2-Feature-Engineering`, `D3c-Feast-Coordination` | Row committed in PostgreSQL |
| S3 | Score an application | `D3-Score-Application`, `D3s-Scoring-Request` | `hc.feature_ready` event |
| S4 | Upload a document | `D4-Upload-Document` | Applicant attaches a file |
| S5 | Warehouse bootstrap and training snapshot | `D5-Warehouse-Bootstrap` | `make k8s-load-dwh`, `k8s-dbt`, `k8s-export-training-snapshot` |
| S6 | Train and register (two paths) | `D6-Train-and-Register` | Data scientist |
| S7 | Promote a model to serving | `D7-Promote-to-Serving` | MLflow stage → Production |
| S8 | Predictor cold start | part of `D7` | New InferenceService pod |
| S9 | End-to-end load test | `D8-Load-Test` | `run_e2e_load_test.sh` |

---

## S1. Submit an application

```mermaid
sequenceDiagram
    autonumber
    actor A as Applicant
    participant ING as ingress-nginx
    participant UI as Streamlit UI
    participant R as API routes
    participant DI as Dependency wiring
    participant WF as SubmitLoanWorkflow
    participant REPO as PostgresLoanRepository
    participant GW as KafkaScoringGateway
    participant PG as PostgreSQL operations
    participant K as Kafka hc.applications.public.loan_applications

    A->>ING: GET / (Minikube IP)
    ING->>UI: proxy :8501
    A->>UI: fill form, Submit
    UI->>R: POST http://api-service/api/v1/applications (24 fields + document_ids)
    Note over R: Pydantic LoanApplicationCreate validation (enums, ranges)
    R->>DI: Depends(get_submit_loan_workflow)
    DI->>REPO: PostgresLoanRepository(AsyncSession)
    DI->>GW: KafkaScoringGateway() creates a NEW Producer ⚠F-05
    R->>WF: execute(SubmitLoanInput)
    WF->>WF: LoanApplication(..., status=SUBMITTED)
    WF->>REPO: save(application)
    REPO->>PG: SELECT * FROM loan_applications WHERE sk_id_curr = ?
    alt row exists
        REPO->>PG: UPDATE non-null columns
    else new
        REPO->>PG: INSERT (flattened document_id_N)
    end
    REPO->>PG: COMMIT
    Note over PG: updated_at trigger fires. The WAL record is now visible to Debezium (S2).
    WF->>GW: publish_for_scoring(sk_id_curr)
    GW->>K: produce {sk_id_curr, type: APPLICATION_SUBMITTED}, acks=all, poll(0), no flush ⚠F-03
    alt BufferError / broker down
        GW-->>WF: error logged and swallowed
    end
    WF-->>R: SubmitLoanOutput(status=SUBMITTED, is_approved=None, risk_score=None)
    R-->>UI: 201 LoanApplicationResponse
    UI-->>A: "Application submitted"
    Note over A,K: No later step returns the decision to the applicant ⚠F-04
```

**Failure behaviour**

| Failure | Result |
|---|---|
| Validation error | 422 from FastAPI |
| PostgreSQL down | Exception → 500 `Failed to create loan application` |
| Kafka down | 201 returned anyway. Scoring still happens because CDC is independent of this publish. |
| Same `sk_id_curr` submitted twice | Row updated. Debezium emits `op=u`, and the whole pipeline runs again. |

## S2. CDC fan-out and feature engineering

```mermaid
sequenceDiagram
    autonumber
    participant PG as PostgreSQL WAL
    participant DBZ as Debezium connector
    participant T0 as hc.applications.public.loan_applications
    participant FC as Flink CDC job
    participant BS as Bureau service
    participant CHX as ClickHouse application_external
    participant TR as hc.application_ext_raw
    participant FB as Flink bureau job
    participant DS as DWH service
    participant CHM as ClickHouse application_mart
    participant TA as hc.application_features
    participant TE as hc.application_ext
    participant TD as hc.application_dwh
    participant FS as Feast materialiser
    participant RD as Redis
    participant TF as hc.feature_ready

    DBZ->>PG: logical replication slot debezium_slot (pgoutput)
    PG-->>DBZ: INSERT on public.loan_applications
    DBZ->>T0: envelope {schema, payload: {before: null, after: row, op: c, source, ts_ms}}
    Note over T0: The API's plain {sk_id_curr, type} message is on this topic too ⚠F-03

    par Applicant features
        FC->>T0: poll (group flink-cdc-applications)
        Note over FC: debezium-json decoding. The API message fails to parse and is ignored.
        FC->>FC: safe_parse_decimal, days_birth = birth - created (negative)
        FC->>FC: days_employed = created - start (POSITIVE) ⚠F-01
        FC->>FC: document_flag(document_id_2..21), ts = UNIX_TIMESTAMP()
        FC->>TA: upsert key=sk_id_curr
    and Bureau features
        BS->>T0: consume(50) (group external-bureau-service, auto-commit) ⚠F-06
        Note over BS: Both the Debezium event and the API message match, so each id is processed twice
        BS->>CHX: SELECT * FROM bureau WHERE SK_ID_CURR = id (full scan) ⚠F-09
        CHX-->>BS: bureau rows
        BS->>CHX: SELECT * FROM bureau_balance WHERE SK_ID_BUREAU IN (...)
        BS->>CHX: SELECT * FROM external_score WHERE SK_ID_CURR = id LIMIT 1
        BS->>TR: {sk_id_curr, bureau[], bureau_balance[], external_scores{}, ts} + traceparent
        FB->>TR: poll (group flink-bureau-aggregation, format raw)
        FB->>FB: aggregate_bureau_features() gives ~60 BUREAU_* (2nd implementation) ⚠F-02
        FB->>TE: upsert key=sk_id_curr
    and Internal history features
        DS->>T0: consume(50) (group dwh-features-service, auto-commit)
        DS->>CHM: SELECT * FROM mart_previous_application / mart_pos_cash_balance / mart_credit_card_balance WHERE SK_ID_CURR = id
        DS->>DS: flatten row 0 of each mart, every column (None if missing)
        DS->>TD: {sk_id_curr, ts, PREV_*, POS_*, CC_*}
    end

    par per source (application, external, dwh)
        FS->>TA: poll (feast-materializer-application)
        FS->>TE: poll (feast-materializer-external)
        FS->>TD: poll (feast-materializer-dwh)
    end
    loop each flusher: every 200 rows or 300 ms
        FS->>RD: write_to_online_store(view, DataFrame) in DB 0
        loop each row in the batch
            FS->>RD: EVALSHA in DB 1: SADD feature_coordination:id source, EXPIRE 300, SCARD
            RD-->>FS: count
            alt count == 3
                FS->>TF: send {sk_id_curr, source, ts}
                Note over FS,TF: Sent again on every later write for this id within the TTL ⚠F-03
            else count < 3
                FS->>FS: wait for the remaining sources
            end
        end
    end
```

**Timing.** The three branches race. Readiness is decided by whichever source completes the set last, usually the bureau branch, which needs two Kafka hops, a full-scan ClickHouse query and a Flink UDF.

## S3. Score an application

```mermaid
sequenceDiagram
    autonumber
    participant TF as hc.feature_ready
    participant KS as KafkaSource feature-ready-source
    participant CH as Sequence KafkaChannel (8 partitions)
    participant DSP as kafka-channel-dispatcher
    participant QP as queue-proxy
    participant SV as scoring service :3000
    participant REG as serving-minio registry.db
    participant RD as Redis DB 0
    participant OUT as KafkaSink scoring-output-sink
    participant DLQ as KafkaSink scoring-dlq-sink
    participant TS as hc.scoring
    participant TQ as hc.scoring.dlq

    KS->>TF: poll (group knative-scoring-consumer, 8 consumers on 4 partitions)
    KS->>CH: POST CloudEvent (data = {sk_id_curr, source, ts})
    alt channel unavailable after retry 3 (exponential, 1 s)
        KS->>DLQ: dead letter
        DLQ->>TQ: produce
    end
    DSP->>CH: consume (subscriber group for scoring-pipeline-kn-sequence-0)
    Note over DSP,CH: Measured bottleneck: ~4k message lag on this group, 502s from the predictor ⚠F-11
    DSP->>QP: POST /v1/score-by-id
    QP->>SV: forward to 127.0.0.1:3000
    SV->>SV: json.loads(raw body), unwrap CloudEvent, ScoreByIdRequest
    SV->>SV: ensure_model_loaded() (no-op when warm)
    SV->>REG: FeatureStore(...) loads registry.db on every request ⚠F-10
    SV->>RD: get_online_features(application_features:*, external_features:*, dwh_features:*)
    alt no feature data and require_customer_data
        SV-->>QP: 200 CloudEvent {decision: under-review, reason: feature_data_unavailable}
    else features found
        SV->>SV: map to 24 model columns, one-row DataFrame
        SV->>SV: predict_proba (nthread=1), threshold 0.3 gives approve or reject
        SV-->>QP: 200 CloudEvent {sk_id_curr, probability, decision, threshold, model, version, ts}
    end
    SV->>SV: log score_by_id_timing (per-stage ms)
    QP-->>DSP: response
    alt 5xx or connection reset, after retry 3
        DSP->>DLQ: dead letter
        DLQ->>TQ: produce
    else 2xx
        DSP->>OUT: forward reply (Sequence reply ref)
        OUT->>TS: produce, binary content mode (body = JSON, ce_* headers)
    end
    Note over TS: No consumer in the platform ⚠F-04
```

## S4. Upload a document

```mermaid
sequenceDiagram
    autonumber
    actor A as Applicant
    participant UI as Streamlit UI (pod)
    participant API as Loan Application API
    participant S3 as MinIO loan-documents

    A->>UI: choose file + document type (2..21)
    UI->>API: POST /api/v1/presigned-url {sk_id_curr, document_type, file_extension}
    API->>API: validate type and extension (pdf, jpg, jpeg, png), sanitise sk_id_curr
    API->>S3: presigned_put_object(loan-documents, {sk}/{folder}/doc_uuid.ext, expiry)
    API-->>UI: {upload_url, document_id}
    UI->>S3: PUT bytes to upload_url (from the pod, not the browser)
    S3-->>UI: 200
    UI->>API: POST /api/v1/applications with document_ids {document_id_N: doc_...}
    Note over API: Stored as document_id_N, becomes flag_document_N in the Flink CDC job. The document content is never read.
```

## S5. Warehouse bootstrap and training snapshot

```mermaid
sequenceDiagram
    autonumber
    actor E as Platform engineer
    participant MK as minikube mount
    participant J1 as Job clickhouse-init-schema
    participant J2 as Job clickhouse-load-data
    participant CH as ClickHouse
    participant DBT as Job dbt-transform
    participant TM as training-minio

    E->>MK: make k8s-load-dwh mounts ./data at /mnt/data (uid 101)
    E->>J1: apply 02-clickhouse-init.yaml
    J1->>CH: CREATE DATABASE application_dwh, application_external (+ otel tables in default)
    E->>J2: apply
    loop each CSV
        J2->>J2: clickhouse-local DESCRIBE file() infers the schema
        J2->>CH: CREATE TABLE ... ENGINE = MergeTree() ORDER BY tuple() ⚠F-09
        alt table already has rows
            J2->>J2: skip
        else empty
            J2->>CH: INSERT ... FORMAT CSVWithNames (stdin stream)
        end
    end
    E->>MK: unmount
    E->>DBT: make k8s-dbt
    DBT->>CH: staging views, then mart tables in application_mart
    E->>CH: make k8s-export-training-snapshot
    CH->>TM: INSERT INTO FUNCTION s3(.../ds=2025-09-19/loan_applications.csv) SELECT mart_application JOIN mart_application_train
    Note over TM: Application columns and TARGET only. No bureau, previous, POS or CC features ⚠F-08
```

## S6. Train and register

```mermaid
sequenceDiagram
    autonumber
    actor DSC as Data scientist
    participant WS as Workstation scripts
    participant KFP as Kubeflow Pipelines
    participant RAY as RayCluster
    participant TM as training-minio
    participant ML as MLflow
    participant MA as MLflow MinIO

    rect rgb(235, 242, 255)
    Note over DSC,MA: Path A, local (the README path, produces the 24-feature model)
    DSC->>WS: python notebook/model_pipeline.py
    WS->>WS: 5-fold CV, Optuna TPE (XGBoost vs CatBoost), calibration, PR-curve threshold
    WS-->>DSC: data/best_model_config.json
    DSC->>WS: train_register.py --data complete_feature_dataset.csv --config ... --stage Production
    WS->>WS: stratified 80/20, ClipQuantiles + SimpleImputer + OrdinalEncoder + XGBClassifier
    WS->>WS: AUC, AUC-PR, Brier, ECE, precision, recall, F1 at threshold
    WS->>ML: log_params, log_metric, log_model(registered_model_name=credit_risk_model)
    WS->>MA: model/ + feast_metadata.yaml (selected_features, mapping, model_signature)
    opt --stage
        WS->>ML: transition_model_version_stage(version, Production)
    end
    end

    rect rgb(240, 250, 240)
    Note over DSC,MA: Path B, Kubeflow
    DSC->>KFP: run training_pipeline.yaml (training_param.yaml)
    KFP->>TM: fetch_minio_snapshot
    KFP->>RAY: ray_tune_hyperparams (ASHA, 5 dimensions; in-pod Ray if no ray_address)
    KFP->>KFP: train_and_register on all snapshot columns except TARGET ⚠F-08
    KFP->>KFP: 1000-sample bootstrap CIs
    KFP->>ML: register + stage
    KFP->>MA: model + feast_metadata.yaml
    end
```

## S7. Promote a model to serving

```mermaid
sequenceDiagram
    autonumber
    actor DSC as Data scientist
    participant ML as MLflow
    participant MW as mlflow-watcher
    participant K8 as Kubernetes API
    participant BB as Job bento-builder-vN
    participant GH as GitHub
    participant SM as serving-minio bentoml-bundles
    participant SW as serving-watcher + DinD
    participant IR as docker-registry :5000
    participant KC as KServe controller
    participant SEQ as Sequence scoring-pipeline

    DSC->>ML: transition version N to Production
    loop every 10 s
        MW->>ML: search versions, stage == Production?
    end
    MW->>K8: create Job from job-template.yaml (MODEL_URI=models:/credit_risk_model/N, VERSION_TAG=vN)
    K8->>BB: schedule
    BB->>GH: git clone APP_REPO@APP_REF
    BB->>ML: mlflow.sklearn.load_model(MODEL_URI)
    BB->>BB: joblib.dump to application/scoring/bundle/model.joblib, bentoml build --version vN
    BB->>SM: upload Bento dir to bentos/credit_risk_model/vN/
    loop every 30 s
        SW->>SM: list_objects_v2(prefix bentos/credit_risk_model/), sort v* descending
    end
    SW->>SW: targets = newest 2. New = targets minus deployed (in memory) ⚠F-12
    SW->>SM: download Bento vN
    SW->>SW: patch env/docker/Dockerfile ($BENTO_PATH, uv, protobuf 5.29.0)
    SW->>IR: docker build + push credit-risk-scoring:vN
    SW->>K8: create or patch InferenceService credit-risk-vN (RawDeployment)
    K8->>KC: reconcile, creates a Deployment + Service
    SW->>SEQ: patch spec.steps[0].ref.name = credit-risk-vN (last version processed, set order) ⚠F-12
    SW->>K8: delete InferenceServices not in targets
    Note over SEQ: Cut-over is immediate. No canary, no shadow traffic, no automatic rollback.
```

## S8. Predictor cold start

```mermaid
sequenceDiagram
    autonumber
    participant P as predictor pod
    participant B as bundle/model.joblib
    participant REG as registry.db (serving-minio)
    participant RD as Redis

    P->>P: bentoml.importing() imports runtime-only deps
    P->>P: startup hook calls ensure_model_loaded() under _init_lock
    P->>B: load_model(source=local)
    B-->>P: sklearn Pipeline + feast_metadata
    alt no feast_metadata or no selected_features
        P->>P: RuntimeError, pod CrashLoopBackOff
    end
    P->>P: _resolve_feast_repo_path() writes inline feature_store.yaml to a temp dir
    P->>REG: FeatureStore.list_stream_feature_views()
    P->>P: for each selected feature, find view:name
    alt a feature is missing in every view
        P->>P: RuntimeError, refuse to serve
    end
    P->>P: ready, /healthz returns model + version
    Note over P,RD: Redis is first used on the first request, not at startup
```

## S9. End-to-end load test

```mermaid
sequenceDiagram
    autonumber
    actor E as Platform engineer
    participant L as Locust workers
    participant PB as PgBouncer :6432
    participant PG as PostgreSQL
    participant PIPE as CDC, features, scoring (S2, S3)
    participant TS as hc.scoring / hc.scoring.dlq
    participant M as capture scripts

    E->>M: snapshot cAdvisor, KafkaChannel offsets
    E->>L: USERS=10 SPAWN_RATE=2 RUN_TIME=3m
    loop each user task
        L->>PB: INSERT INTO loan_applications (psycopg2 pool 5..20)
        PB->>PG: session-pooled insert (p95 3 ms)
    end
    Note over L,PG: Bypasses the API, so the dual write (F-03) is not exercised
    PG-->>PIPE: WAL, then S2 and S3
    PIPE->>TS: decisions
    L->>TS: per-worker consumer group, correlate by sk_id_curr, record E2E latency
    E->>M: end snapshot gives CFS throttling, restarts, channel lag
    Note over E,M: Last run: 5,458 inserts, 5,198 feature_ready, 912 scoring (17.5%), 0 DLQ
```

## Failure-mode summary

| Component fails | Immediate effect | Data loss? | Recovery |
|---|---|---|---|
| API pod | 1 of 2 replicas serves | No | K8s restart |
| PostgreSQL | Submissions fail (500) | No (PVC) | StatefulSet restart. The Debezium slot holds the WAL. |
| Debezium | Events stop | No (slot retains the WAL; disk grows) | Restart. Resumes from the slot. |
| Kafka broker (RF 1) | Everything stops | Possible (single replica) | Restart. Producers retry. |
| Flink job | No `hc.application_features` / `hc.application_ext` | No, but full replay from earliest on restart (no checkpoints) | Re-submit Job |
| Bureau / DWH service mid-batch | Batch partly produced | **Yes**: auto-committed offsets | None |
| Feast materialiser mid-batch | Buffered rows lost | **Yes** | None; the coordination key expires |
| Redis | Features and coordination lost (no persistence) | **Yes** | Re-run the pipeline for affected ids |
| Predictor 5xx | 3 retries, then DLQ | No (DLQ) | Manual replay from `hc.scoring.dlq` |
| MLflow / GitHub down during promotion | Bento build fails | No | Re-promote; the watcher retriggers only when the version changes |
