/*
 * Credit Risk Decisioning Platform — C4 model (Structurizr DSL).
 *
 * Source of truth for the architecture diagrams in docs/architecture/.
 * Describes the system AS BUILT in this repository (Minikube / Kubernetes path, ADR-0005),
 * not an idealised target. Known gaps are modelled explicitly with the "Gap" and "Risk" tags
 * so they render in red/dashed on every view; see docs/architecture/c4/README.md#findings.
 *
 * View locally:  docker run -it --rm -p 8081:8080 -v "$PWD/docs/architecture/c4:/usr/local/structurizr" structurizr/structurizr local
 * Validate:      docker run --rm -v "$PWD/docs/architecture/c4:/usr/local/structurizr" structurizr/structurizr validate -w /usr/local/structurizr/workspace.dsl
 * Export:        see docs/architecture/c4/README.md
 *
 * Verified against the code on 2026-11-21 (commit 7605340).
 */
workspace "Credit Risk Decisioning Platform" "Event-driven loan scoring: CDC -> stream features -> Feast/Redis -> KServe, on Minikube." {

    !identifiers hierarchical

    model {
        properties {
            "structurizr.groupSeparator" "/"
        }

        # ------------------------------------------------------------------
        # People
        # ------------------------------------------------------------------
        applicant = person "Loan applicant / loan officer" "Fills in the loan application and uploads supporting documents through the web UI. Never sees the decision (no read-back path exists)."
        scientist = person "Data scientist" "Explores data in notebooks, tunes and trains models, registers them in MLflow and promotes a version to the Production stage."
        engineer = person "Platform engineer" "Builds images, deploys the stack with the Makefile, port-forwards tools, runs load tests and reads dashboards."

        # ------------------------------------------------------------------
        # External software systems
        # ------------------------------------------------------------------
        kaggle = softwareSystem "Home Credit Default Risk dataset" "Kaggle CSVs (~3 GB, 307,511 applications, 8.1% default). Stand-in for BOTH the lender's internal history and the external credit bureau." "External"
        registries = softwareSystem "Public container registries" "Docker Hub (ngnquanq/credit-risk-api, -consumers, feast-repo:v18, confluentinc/*, debezium/*, clickhouse/*, redis, minio) and other public images." "External"
        github = softwareSystem "GitHub" "Hosts the repository. GitHub Actions runs 6 test gates (but triggers on 'main' while the default branch is 'master'). The bento-builder Job git-clones the repo at build time." "External"
        decisionConsumer = softwareSystem "Decision consumer (not built)" "Whatever should act on hc.scoring: write the decision back to PostgreSQL, notify the applicant, feed a rules engine. Does not exist; the decision loop is open." "External,Gap"

        # ------------------------------------------------------------------
        # The system
        # ------------------------------------------------------------------
        crs = softwareSystem "Credit Risk Decisioning Platform" "Takes a loan application, engineers features from internal history and bureau data in real time, scores default risk with XGBoost, and publishes a decision event." {
            !docs docs

            # ============ Intake plane ============
            group "1 Intake (ns: api-gateway)" {
                ingress = container "Ingress controller" "Minikube ingress-nginx addon. Routes '/' -> frontend-service:8501 and '/api(/|$)(.*)' -> api-service:80 (rewrite-target /$2)." "ingress-nginx" "Infra"

                frontend = container "Loan application UI" "Server-rendered form for applicant details and document upload. Calls the API from the pod (API_BASE_URL=http://api-service), not from the browser." "Python, Streamlit :8501" "Web" {
                    properties {
                        "source" "application/frontend/frontend.py, utils.py"
                        "k8s" "Deployment frontend-service, ns api-gateway"
                    }
                }

                api = container "Loan Application API" "Accepts applications, persists them, issues pre-signed upload URLs. Clean Architecture layering (entrypoints -> workflows -> domain ports <- infrastructure adapters)." "Python 3.10, FastAPI, SQLAlchemy async, asyncpg :8000" {
                    properties {
                        "source" "application/entrypoints/api, workflows, domain, infrastructure, core"
                        "k8s" "Deployment api-service x2, ns api-gateway, image ngnquanq/credit-risk-api:latest"
                    }
                    routes = component "HTTP routes" "GET /health; POST /api/v1/presigned-url; POST /api/v1/applications; GET /api/v1/applications/{id}; GET /api/v1/applications/{id}/status. Swagger only when DEBUG." "FastAPI router (entrypoints/api/main.py)"
                    deps = component "Dependency wiring" "Per-request construction of repository, gateway and workflow. Builds a NEW Kafka Producer for every request." "FastAPI Depends (entrypoints/api/dependencies.py)" "Risk"
                    workflow = component "SubmitLoanWorkflow" "Use case: build LoanApplication entity -> status SUBMITTED -> repo.save() -> gateway.publish_for_scoring() -> return pending (is_approved=None)." "Python (workflows/submit_loan.py)"
                    domain = component "Domain model and ports" "LoanApplication entity, ApplicationStatus enum; ports LoanRepository and ScoringGateway (abstract)." "Python (domain/)"
                    repo = component "PostgresLoanRepository" "Upsert by sk_id_curr; flattens document_ids into document_id_N columns. Write-only: no read method." "SQLAlchemy async (infrastructure/persistence/postgres_loan_repo.py)"
                    scoringGateway = component "KafkaScoringGateway" "Produces {sk_id_curr, type: APPLICATION_SUBMITTED} with acks=all, poll(0), no flush, errors swallowed. Target topic = the Debezium CDC topic (config.kafka_application_topic)." "confluent-kafka (infrastructure/external/kafka_scoring.py)" "Risk"
                    docAdapter = component "Document storage adapter" "Validates type 2-21 and extension (pdf/jpg/jpeg/png), sanitises sk_id_curr, issues presigned PUT for {sk_id_curr}/{folder}/{doc_id}.{ext}." "minio-py (entrypoints/api/main.py)"
                    persistenceModels = component "Persistence models and session" "SQLAlchemy tables loan_applications and application_status_log; Pydantic request/response schemas; async engine + session factory." "SQLAlchemy, Pydantic v2 (infrastructure/persistence/models, core/database.py)"
                    apiTracing = component "Tracing setup" "OpenTelemetry tracer 'api-service', 10% sampling, FastAPI auto-instrumentation, OTLP gRPC exporter." "OpenTelemetry (core/tracing)"
                    apiKeyGuard = component "API key guard" "PLANNED (E9). FastAPI dependency on every /api/v1 route: compares X-API-Key with keys from settings (SecretStr); 401 otherwise. /health stays open. CORS limited to configured origins." "FastAPI Depends" "Planned"
                }
            }

            # ============ Operational data plane ============
            group "2 Operational data (ns: data-services)" {
                opsDb = container "Operational database" "Database 'operations'. Tables: loan_applications (PK sk_id_curr, 24 applicant fields + document_id_2..21, created_at/updated_at trigger) and application_status_log (event-sourced status; nothing writes to it). wal_level=logical, publication debezium_pub, slot debezium_slot." "PostgreSQL 15 (StatefulSet ops-postgres)" "Database"
                pgbouncer = container "Connection pooler" "Listens :6432, pool_mode=session, max_client_conn=1000, default_pool_size=200. Used by the load-test harness and port-forwards; the API connects to PostgreSQL directly." "PgBouncer" "Infra"
                docStore = container "Document object store" "Bucket loan-documents, keys {sk_id_curr}/{identity|financial/*|employment|personal|other}/doc_<uuid>.<ext>. Not read by any feature pipeline." "MinIO (data-minio-server)" "Storage"
                debezium = container "CDC connector" "Connector postgres-application-connector: PostgresConnector, plugin pgoutput, table.include.list=public.loan_applications, topic.prefix=hc.applications, snapshot.mode=initial, decimal.handling.mode=double. Registered by a curl init container." "Kafka Connect, Debezium 2.7.3" "Infra"
                kafka = container "Event broker" "Single node, KRaft (broker,controller), PLAINTEXT kafka-broker.data-services:9092. Topics created by Job kafka-create-topics with 4 partitions, replication factor 1." "Apache Kafka (confluentinc/cp-kafka 7.7.1)" "Infra"
                schemaRegistry = container "Schema registry" "Deployed but unused: every topic carries schemaless JSON (Debezium embeds its schema inline)." "Confluent Schema Registry 7.7.1" "Infra,Unused"
                kafkaUi = container "Kafka UI" "Topic / consumer-group browser for engineers (make pf-kafka-ui -> :8080)." "provectuslabs/kafka-ui" "Tool"

                group "Kafka topics (4 partitions, RF 1)" {
                    tCdc = container "hc.applications.public.loan_applications" "Debezium change events for loan_applications (envelope with schema + payload.before/after/op). ALSO receives plain {sk_id_curr,type} messages from the API (dual write)." "Kafka topic, JSON" "Topic"
                    tAppFeatures = container "hc.application_features" "One row per application: 23 applicant features + days_birth/days_employed + flag_document_2..21 + ts. Upsert stream keyed by sk_id_curr." "Kafka topic, upsert JSON" "Topic"
                    tExtRaw = container "hc.application_ext_raw" "Raw bureau rows, bureau_balance rows and ext_source_1..3 for one sk_id_curr, plus ts." "Kafka topic, JSON" "Topic"
                    tExt = container "hc.application_ext" "Aggregated bureau features (~60 BUREAU_*) + ext_source_1..3 + ts. Upsert stream keyed by sk_id_curr." "Kafka topic, upsert JSON" "Topic"
                    tDwh = container "hc.application_dwh" "Flattened customer-grain mart rows (PREV_*, POS_*, CC_*) + ts, keyed by sk_id_curr." "Kafka topic, JSON" "Topic"
                    tReady = container "hc.feature_ready" "{sk_id_curr, source, ts} emitted once all three feature groups are in Redis (and again on every later write for that id)." "Kafka topic, JSON" "Topic"
                    tScoring = container "hc.scoring" "Decision events {sk_id_curr, probability, decision, threshold, model, version, ts} or {decision: under-review, reason: feature_data_unavailable}. No consumer in the platform." "Kafka topic, JSON (binary content mode)" "Topic"
                    tDlq = container "hc.scoring.dlq" "Events that exhausted 3 exponential retries at the KafkaSource or the Sequence step." "Kafka topic, JSON" "Topic"
                    tTimeout = container "hc.feature_timeout" "PLANNED (E3). {sk_id_curr, missing_groups, first_seen_ts} for applications whose feature groups never completed." "Kafka topic, JSON" "Topic,Planned"
                }
            }

            # ============ Stream feature engineering ============
            group "3 Stream feature engineering (ns: data-services)" {
                flink = container "Stream processing cluster" "Session cluster: 1 JobManager, 2 TaskManagers x 8 slots. Jobs submitted by K8s Jobs flink-submit-cdc and flink-submit-bureau. No checkpointing configured, so a restart replays the CDC topic from earliest (F-13)." "Apache Flink 1.17, PyFlink Table API (image flink-pyflink:latest)" "Risk" {
                    properties {
                        "source" "application/flink/jobs"
                    }
                    cdcJob = component "CDC application ETL job" "Source loan_applications_cdc (format debezium-json, schema-include, ignore-parse-errors, group flink-cdc-applications, earliest-offset) -> INSERT INTO application_features (upsert-kafka, key raw sk_id_curr, value json). ts = UNIX_TIMESTAMP() at processing time. Reads code_gender but does not emit it, so the 24-feature model cannot resolve CODE_GENDER (F-07)." "Flink SQL (cdc_application_etl.py)" "Risk"
                    cdcUdfs = component "CDC UDFs" "safe_parse_decimal / decode_decimal_base64 (Debezium decimals), calculate_days_birth = birth - created (negative), calculate_days_employed = created - start (POSITIVE: opposite sign to training data), document_flag." "PyFlink scalar UDFs (cdc_udfs.py)" "Risk"
                    bureauJob = component "Bureau aggregation job" "Source external_raw (format raw, group flink-bureau-aggregation) -> UDF -> INSERT INTO external_features (upsert-kafka)." "Flink SQL (bureau_aggregation_etl.py)"
                    bureauUdfs = component "Bureau aggregation UDF" "aggregate_bureau_features(): counts, active/closed sums, debt/credit ratios, overdue maxima, bureau_balance DPD stats -> ~60 BUREAU_* features. Second implementation of the dbt mart_bureau_features logic." "PyFlink UDF (bureau_aggregation_udfs.py)" "Risk"
                }

                bureauConsumer = container "External bureau service" "Fetches the applicant's bureau history for every CDC event and republishes it raw for Flink." "Python 3.10, asyncio, confluent-kafka, clickhouse-connect" {
                    properties {
                        "source" "application/entrypoints/bureau_consumer.py, infrastructure/external/bureau_client.py"
                        "k8s" "Deployment bureau-consumer, HPA 2-6 @70% CPU (topic has 4 partitions)"
                    }
                    bLoop = component "Batch consume loop" "consume(50, 0.5s) -> parse -> asyncio.gather under Semaphore(20) -> produce -> flush. Group external-bureau-service, auto.offset.reset=latest, enable.auto.commit=true; failures are logged and dropped." "ExternalBureauService.run()" "Risk"
                    bExtract = component "CDC id extractor" "Reads sk_id_curr from payload.after/before or a plain dict, so it also accepts the API's direct message (each application processed twice)." "_extract_sk_id_curr_from_cdc()"
                    bClient = component "Bureau client" "Pool of 20 ClickHouse clients. SELECT * FROM bureau WHERE SK_ID_CURR=?; SELECT * FROM bureau_balance WHERE SK_ID_BUREAU IN (...); SELECT * FROM external_score ... LIMIT 1. Run via asyncio.to_thread." "clickhouse-connect"
                    bProducer = component "Raw producer" "Produces to hc.application_ext_raw with W3C trace headers, key sk_id_curr." "confluent-kafka Producer"
                }

                dwhConsumer = container "DWH features service" "Looks up the applicant's internal history in the dbt marts for every CDC event and publishes a flat record." "Python 3.10, asyncio, confluent-kafka, clickhouse-connect" {
                    properties {
                        "source" "application/entrypoints/feature_consumer.py, infrastructure/external/dwh_client_ch.py"
                        "k8s" "Deployment feature-consumer, HPA 2-6 @70% CPU (topic has 4 partitions)"
                    }
                    dLoop = component "Batch consume loop" "Same pattern as the bureau service. Group dwh-features-service, latest, auto-commit, drop on error." "DWHFeaturesService.run()" "Risk"
                    dExtract = component "CDC id extractor" "Same extractor as the bureau service." "_extract_sk_id_curr_from_cdc()"
                    dClient = component "DWH client" "fetch_all_by_sk_id_curr() over MART_TABLES = mart_previous_application, mart_pos_cash_balance, mart_credit_card_balance; column lists from system.columns." "clickhouse-connect"
                    dFlatten = component "Schema-driven flattener" "Emits every mart column (None when missing) from row 0 of each table, lower-cased, + sk_id_curr + ts." "process_loan_application()"
                }
            }

            # ============ Warehouse ============
            group "4 Warehouse (ns: data-services)" {
                chExternal = container "Bureau store (simulated credit bureau)" "Database application_external: bureau (~1.7M rows), bureau_balance (~27M rows), external_score (EXT_SOURCE_1..3). MergeTree ORDER BY tuple(): no primary key, so every per-applicant lookup is a full scan." "ClickHouse 25.6 (clickhouse-server-0)" "Database,Risk"
                chDwh = container "Raw internal history" "Database application_dwh: application_train/test, previous_application, installments_payments, POS_CASH_balance, credit_card_balance loaded from CSV (schema inferred by clickhouse-local)." "ClickHouse 25.6 (clickhouse-server-0)" "Database"
                chMart = container "Feature marts" "Database application_mart (dbt): mart_application, mart_application_train, mart_bureau_features, mart_previous_application, mart_pos_cash_balance, mart_credit_card_balance (customer grain)." "ClickHouse 25.6 (clickhouse-server-0)" "Database"
                chLoader = container "Warehouse loader" "Jobs clickhouse-init-schema and clickhouse-load-data: create databases, stream CSVs from the minikube mount /mnt/data via stdin, skip non-empty tables." "K8s Jobs, bash + clickhouse-client" "Job"
                dbt = container "Feature mart transformations" "Project ml_data_mart: staging views (stg_application_train) and mart tables, macro select_with_assume_not_null. Run as Job dbt-transform." "dbt-core + dbt-clickhouse (image dbt-clickhouse:latest)" "Job" {
                    stg = component "Staging models" "stg_application_train: renames, EXT_SOURCE null handling. Materialised as views." "dbt SQL (models/staging)"
                    marts = component "Mart models" "Customer-grain aggregates: PREV_* (refusal rate, annuity mean, goods/credit), POS_* (contract length, DPD, months observed), CC_* (utilisation, DPD), BUREAU_* (debt/credit, active sums, overdue). Materialised as tables." "dbt SQL (models/mart)"
                }
            }

            # ============ Feature platform ============
            group "5 Feature platform (ns: feature-registry)" {
                feastApply = container "Feature registration job" "feast apply: entity customer (join key sk_id_curr, STRING), StreamFeatureViews application_features (TTL 1d), external_features (7d), dwh_features (7d), FeatureService realtime_scoring_v1. Schemas generated from sampled Kafka messages." "K8s Job, Feast 0.40 (ngnquanq/feast-repo:v18)" "Job"
                feastStream = container "Feast stream materialiser" "Consumes the three feature topics, micro-batches writes into the online store and decides when an application is complete." "Python 3.10, kafka-python, Feast SDK, redis-py" {
                    properties {
                        "source" "application/feast_repo/stream_processor.py, redis_coordination.lua"
                        "k8s" "Deployment feast-stream, HPA 2-6, ns feature-registry"
                    }
                    fConsumers = component "Topic consumer threads" "One KafkaConsumer per topic: groups feast-materializer-{application|external|dwh}, auto_offset_reset=latest, enable_auto_commit=true. Each message is submitted to a 20-worker ThreadPoolExecutor (unbounded queue)." "kafka-python" "Risk"
                    fBuffers = component "Micro-batch buffers and flushers" "Per-source in-memory queue.Queue; one flusher thread per source flushes at 200 rows or 300 ms. Lost on pod crash." "Python threads" "Risk"
                    fWriter = component "Online store writer" "Builds one DataFrame per batch from the feature view schema, adds event_timestamp, calls FeatureStore.write_to_online_store()." "Feast SDK"
                    fCoord = component "Completeness coordinator" "Per sk_id_curr: EVALSHA Lua {SADD feature_coordination:<id> <source>; EXPIRE 300; return SCARD}. Count == 3 -> ready. Works across replicas because state lives in Redis DB 1." "Redis Lua script"
                    fReady = component "Readiness publisher" "Produces {sk_id_curr, source, ts} to hc.feature_ready. Fires on EVERY write once the set is full, so duplicates or late sources re-trigger scoring." "kafka-python Producer" "Risk"
                    readiness = component "Readiness coordinator" "PLANNED (E3). register_arrival(sk_id_curr, group) -> PENDING | READY_FIRST_TIME | ALREADY_READY. Lua: SADD + EXPIRE, then SET dispatched:<id> NX so readiness fires exactly once; a sweeper turns expired partial sets into TIMED_OUT." "Python module + Redis Lua" "Planned"
                }
                redis = container "Online store" "DB 0: Feast online features (entity key serialisation v2). DB 1: completeness sets feature_coordination:<sk_id_curr> with 300 s TTL. Single replica, no persistence configured." "Redis 7 (alpine)" "Database"
            }

            # ============ Scoring / serving ============
            group "6 Scoring (ns: kserve, knative-eventing, model-serving)" {
                kafkaSource = container "Feature-ready event source" "KafkaSource feature-ready-source: topic hc.feature_ready, consumerGroup knative-scoring-consumer, consumers 8 (topic has 4 partitions), initialOffset latest, retry 3 exponential PT1S, dead letter -> scoring-dlq-sink." "Knative Eventing KafkaSource" "Eventing"
                sequence = container "Scoring sequence" "Sequence scoring-pipeline with a KafkaChannel template (8 partitions, RF 1). Single step: InferenceService credit-risk-vN at /v1/score-by-id (retry 3, DLS). Reply -> scoring-output-sink. The step ref is patched by the serving watcher. Measured bottleneck: channel subscriber lag + 502s, consistent with containerConcurrency 1 x max 10 pods (F-11)." "Knative Flows Sequence + KafkaChannel" "Eventing,Risk"
                outputSink = container "Scoring output sink" "KafkaSink scoring-output-sink -> hc.scoring, contentMode binary (plain JSON body, ce-* headers)." "Knative KafkaSink" "Eventing"
                dlqSink = container "Scoring dead-letter sink" "KafkaSink scoring-dlq-sink -> hc.scoring.dlq, contentMode binary." "Knative KafkaSink" "Eventing"

                scoring = container "Credit risk scoring service" "Scores one application by id: Feast online lookup -> 24-feature row -> XGBoost sklearn pipeline (optionally calibrated) -> decision at threshold 0.3. Served as InferenceService credit-risk-vN in KServe serverless mode (Knative KPA, concurrency target 1, containerConcurrency 1, min 3 / max 10 pods, scale-down delay 60 s, 500m-2 CPU, 512Mi-1Gi, port 3000)." "Python, BentoML 1.x service wrapping FastAPI, XGBoost, Feast SDK" {
                    properties {
                        "source" "application/scoring/service.py, pipeline.py, model_registry.py, schemas.py, config.py"
                        "k8s" "InferenceService credit-risk-vN (isvc-template-serverless.yaml) in ns kserve, image docker-registry.model-serving:5000/credit-risk-scoring:vN"
                    }
                    sRoutes = component "Scoring endpoints" "GET /healthz; POST /v1/score (features in body); POST /v1/score-by-id (raw body parse, CloudEvent unwrap, ScoreByIdRequest validation)." "FastAPI app mounted in bentoml.Service credit_risk_scoring"
                    sLoader = component "Model loader" "ensure_model_loaded(): thread-safe lazy load of bundle/model.joblib (SCORING_MODEL_SOURCE=local) or MLflow URI; requires feast_metadata.yaml; resolves feature refs against the live registry and refuses to start if a model feature is missing (it does for CODE_GENDER, F-07)." "model_registry.py + service.py" "Risk"
                    sFeast = component "Feature fetcher" "_fetch_features_from_feast(): builds a NEW FeatureStore (inline YAML: registry s3://feast-registry/..., Redis feast-redis:6379) on every request, get_online_features(entity sk_id_curr). No data -> BentoMLException." "Feast SDK" "Risk"
                    sMapper = component "Feature mapper" "Maps Feast names to model columns via feature_mapping (upper-case), keeps strings for categoricals, logs unmapped / None features; builds a one-row DataFrame in model_signature order (missing -> None)." "_map_feast_features(), _as_dataframe_row()"
                    sPredict = component "Predictor" "_predict_proba_local(): sets XGBoost nthread=1, predict_proba[:,1]; postprocess(prob, threshold 0.3) -> approve/reject." "scikit-learn Pipeline + XGBClassifier, pipeline.py"
                    sEvent = component "CloudEvent responder" "Wraps the result with ce-specversion 1.0, ce-type dev.knative.scoring.response, ce-subject sk_id_curr so the Sequence forwards the reply. Feature miss -> decision under-review." "_cloudevent_response()"
                    sTiming = component "Timing and tracing" "One structured score_by_id_timing log per request (body, parse, validate, load, feast, predict, build ms); OTel tracer scoring-service at 10%." "loguru + OpenTelemetry"
                    sPolicy = component "Decision policy" "PLANNED (E5). decide(score) -> Decision{band, score, reasons}: approve below 0.25, under_review 0.25-0.35, reject above 0.35; bands from versioned config. Replaces pipeline.postprocess." "Python module" "Planned"
                }

                servingWatcher = container "Serving watcher" "Every 30 s: list bentoml-bundles/bentos/credit_risk_model/v*; for the newest MAX_ACTIVE_MODELS=2 not yet deployed: download Bento, patch Dockerfile, docker build + push, create/patch InferenceService, then patch the Sequence step to the last version processed (set order). Deletes older ISVCs. Deployed versions kept in memory only." "Python, kubernetes client, boto3, Docker-in-Docker sidecar" "Controller,Risk"
                imageRegistry = container "In-cluster image registry" "docker-registry.model-serving.svc:5000, holds credit-risk-scoring:vN images built by the serving watcher." "Docker Distribution registry" "Infra"
                servingStore = container "Serving object store" "Buckets bentoml-bundles (built Bentos per version) and feast-registry (feature_repo/registry.db). Must exist before Feast pods start." "MinIO (serving-minio, ns model-serving)" "Storage"
            }

            # ============ Model lifecycle ============
            group "7 Model lifecycle (ns: model-registry, training-data, kubeflow, ray)" {
                workstationTraining = container "Local training toolkit" "notebook/model_pipeline.py (5-fold CV, Optuna TPE for XGBoost vs CatBoost, calibration, PR-curve threshold -> best_model_config.json) and application/training/train_register.py (24 fixed features, clip+impute+ordinal pipeline, metrics AUC/AUC-PR/Brier/ECE, logs model + feast_metadata.yaml). Plus EDA notebooks 01-10." "Python, Jupyter, scikit-learn, XGBoost, CatBoost, Optuna, MLflow client" "Workstation"
                trainingStore = container "Training snapshot store" "Bucket training-data/snapshots/ds=2025-09-19/loan_applications.csv = mart_application INNER JOIN mart_application_train (application columns + TARGET only; no bureau / history features)." "MinIO (training-minio, ns training-data)" "Storage"
                kfp = container "Training pipeline" "KFP v2 pipeline (compiled training_pipeline.yaml, params training_param.yaml) on Kubeflow Pipelines 2.14.3." "Kubeflow Pipelines, KFP SDK v2" {
                    kFetch = component "fetch_minio_snapshot" "boto3 download of the snapshot CSV into a KFP Dataset artifact." "KFP component (python:3.11-slim)"
                    kRay = component "ray_tune_hyperparams" "Ray Tune + ASHA over n_estimators 200-600, max_depth 3-9, lr 0.01-0.2 (log), min_child_weight 1-6, gamma 0-0.3; connects to KubeRay when ray_address is set." "KFP component (rayproject/ray:2.31.0-py39)"
                    kTrain = component "train_and_register" "Trains XGBoost on ALL snapshot columns except TARGET (SK_ID_CURR included as a feature), 1000-sample bootstrap CIs for AUC/accuracy/precision/recall at 0.3, logs model + feast_metadata.yaml, registers and stages." "KFP component (mlflow 2.14.3)" "Risk"
                }
                ray = container "Distributed tuning cluster" "RayCluster raycluster-k8s: 1 head + 2 workers (6 Gi), managed by the KubeRay operator." "Ray 2.31 on KubeRay" "Compute"
                mlflow = container "Experiment tracking and model registry" "Runs, params, metrics, artifacts; registered model credit_risk_model with stages (Production triggers deployment)." "MLflow tracking server (Helm, ns model-registry)"
                mlflowDb = container "Registry backend store" "Runs, experiments, model versions, stages." "PostgreSQL (mlflow-postgresql-0)" "Database"
                mlflowArtifacts = container "Model artifact store" "Model directories (MLmodel, model.pkl, requirements) and feast_metadata.yaml." "MinIO (ns model-registry)" "Storage"
                mlflowWatcher = container "Promotion watcher" "Polls MLflow every 10 s; when the Production version changes (or on first poll) creates a bento-builder Job from /configs/job-template.yaml with MODEL_URI and VERSION_TAG=vN." "Python, MLflow client, kubernetes client" "Controller"
                bentoBuilder = container "Bento builder job" "git clone APP_REPO@APP_REF -> load model from MLflow -> joblib dump to application/scoring/bundle/model.joblib -> bentoml build --version vN -> upload Bento dir to s3://bentoml-bundles/bentos/credit_risk_model/vN/. APP_REF is feature/the-grand-migration, not master (F-16)." "K8s Job, Python, BentoML, boto3" "Job,Risk"
            }

            # ============ Planned (target design) ============
            group "10 Decision delivery (planned, ns: api-gateway)" {
                decisionRecorder = container "Decision recorder" "PLANNED (E5). Consumes hc.scoring and hc.feature_timeout, writes one application_status_log row per decision (idempotent on event id), commits offsets after the write." "Python 3.10, confluent-kafka, SQLAlchemy async" "Planned"
            }
            group "11 Shared libraries (planned)" {
                featureCatalog = container "Feature catalog" "PLANNED (E2). features.yaml + loader: name, dtype, group, training column, nullable, protected, valid range, transform. Generates Feast schemas and the Flink sink column list; validates model feature lists. Versioned with the code." "Python package (credit_features), YAML" "Library,Planned"
                trainingRecipe = container "Training recipe" "PLANNED (E6). One fit/evaluate/register function used by the CLI, the notebook and the Kubeflow component: catalog features only, no protected inputs, metrics incl. dir_gender, model_card.md, MLflow tags git_commit / data_snapshot_id / catalog_version." "Python package" "Library,Planned"
            }

            # ============ Observability ============
            group "8 Observability (ns: monitoring, logging)" {
                prometheus = container "Metrics" "kube-prometheus-stack: Prometheus + operator scraping kubelet/cAdvisor, kube-state-metrics, ServiceMonitors (MLflow, KubeRay, MinIO)." "Prometheus" "Observability"
                grafana = container "Dashboards" "Grafana from kube-prometheus-stack." "Grafana" "Observability"
                elastic = container "Log store and search" "ECK: Elasticsearch (elasticsearch-es-default-0) + Kibana; Filebeat DaemonSet ships container stdout (loguru JSON) from every node." "Elastic Cloud on Kubernetes" "Observability"
                jaeger = container "Trace collector" "OTLP gRPC NodePort 30317, HTTP 30318, UI 30686. Helm chart is in the repo but no Makefile target deploys it; exporters retry and drop when it is absent." "Jaeger" "Observability,Optional"
            }

            # ============ Test harness ============
            group "9 Test harness" {
                loadTest = container "End-to-end load test harness" "Locust users INSERT directly into loan_applications (psycopg2 pool 5-20, bypassing the API) and per-worker Kafka consumers correlate hc.scoring / hc.scoring.dlq; scripts capture KafkaChannel offsets and pod CFS throttling." "Locust, psycopg2, kafka-python (tests/test_load)" "Test"
            }
        }

        # ==================================================================
        # Relationships — intake
        # ==================================================================
        applicant -> crs.ingress "Opens the web UI" "HTTP :80 (Minikube IP)"
        crs.ingress -> crs.frontend "Routes '/'" "HTTP :8501"
        crs.ingress -> crs.api.routes "Routes '/api/*' (rewrite)" "HTTP :80 -> :8000"
        crs.frontend -> crs.api.routes "Submits application JSON, requests presigned URLs, reads application" "HTTP/JSON, http://api-service"
        crs.frontend -> crs.docStore "Uploads document bytes to the presigned URL" "HTTP PUT (S3 presigned)"

        crs.api.routes -> crs.api.deps "Resolves SubmitLoanWorkflow per request" "FastAPI Depends"
        crs.api.deps -> crs.api.workflow "Constructs with repo + gateway" "In-process call"
        crs.api.deps -> crs.api.repo "Constructs with AsyncSession" "In-process call"
        crs.api.deps -> crs.api.scoringGateway "Constructs (new Producer each request)" "In-process call"
        crs.api.routes -> crs.api.workflow "execute(SubmitLoanInput)" "async call"
        crs.api.workflow -> crs.api.domain "Creates LoanApplication, sets status SUBMITTED" "In-process call"
        crs.api.workflow -> crs.api.repo "save(application)" "LoanRepository port"
        crs.api.workflow -> crs.api.scoringGateway "publish_for_scoring(sk_id_curr)" "ScoringGateway port"
        crs.api.repo -> crs.api.domain "Implements LoanRepository" "In-process call"
        crs.api.scoringGateway -> crs.api.domain "Implements ScoringGateway" "In-process call"
        crs.api.repo -> crs.api.persistenceModels "Maps entity <-> ORM rows" "In-process call"
        crs.api.routes -> crs.api.persistenceModels "Reads application / status log directly (GET routes)" "In-process call"
        crs.api.routes -> crs.api.docAdapter "presigned-url requests" "In-process call"
        crs.api.routes -> crs.api.apiTracing "Instrumented by" "In-process call"

        crs.api.persistenceModels -> crs.opsDb "INSERT/UPDATE loan_applications; SELECT loan_applications, application_status_log" "asyncpg :5432 (direct, not via PgBouncer)"
        crs.api.scoringGateway -> crs.tCdc "Produces {sk_id_curr, type} onto the CDC topic (dual write)" "Kafka, acks=all, fire-and-forget" "Risk"
        crs.api.docAdapter -> crs.docStore "Ensures bucket exists, presigns PUT (expiry from settings)" "S3 API"
        crs.api.apiTracing -> crs.jaeger "Exports spans" "OTLP gRPC" "Optional"

        # ==================================================================
        # Relationships — CDC and Kafka plumbing
        # ==================================================================
        crs.debezium -> crs.opsDb "Streams WAL changes for public.loan_applications" "Logical replication (pgoutput), slot debezium_slot"
        crs.debezium -> crs.tCdc "Publishes change events (c/u/d, snapshot r)" "Kafka Connect producer"
        crs.pgbouncer -> crs.opsDb "Pools client sessions" "PostgreSQL :5432"
        crs.kafkaUi -> crs.kafka "Browses topics and consumer groups" "Kafka admin"
        crs.schemaRegistry -> crs.kafka "Stores schemas in _schemas (unused)" "Kafka"

        # ==================================================================
        # Relationships — stream feature engineering
        # ==================================================================
        crs.flink.cdcJob -> crs.tCdc "Consumes change events" "Kafka source, debezium-json, group flink-cdc-applications"
        crs.flink.cdcJob -> crs.flink.cdcUdfs "Calls per row" "In-process call"
        crs.flink.cdcJob -> crs.tAppFeatures "Upserts application feature rows" "upsert-kafka, key sk_id_curr"
        crs.flink.bureauJob -> crs.tExtRaw "Consumes raw bureau payloads" "Kafka source, format raw, group flink-bureau-aggregation"
        crs.flink.bureauJob -> crs.flink.bureauUdfs "Aggregates per payload" "In-process call"
        crs.flink.bureauJob -> crs.tExt "Upserts bureau feature rows" "upsert-kafka, key sk_id_curr"

        crs.bureauConsumer.bLoop -> crs.tCdc "Consumes change events (and API messages)" "Kafka, group external-bureau-service, auto-commit"
        crs.bureauConsumer.bLoop -> crs.bureauConsumer.bExtract "Extracts sk_id_curr" "In-process call"
        crs.bureauConsumer.bLoop -> crs.bureauConsumer.bClient "fetch_bureau_by_loan_id + fetch_external_scores (20 concurrent)" "In-process call"
        crs.bureauConsumer.bLoop -> crs.bureauConsumer.bProducer "Produces result + trace headers" "In-process call"
        crs.bureauConsumer.bClient -> crs.chExternal "SELECT bureau, bureau_balance, external_score by id" "ClickHouse HTTP :8123"
        crs.bureauConsumer.bProducer -> crs.tExtRaw "Publishes raw bureau payload" "Kafka, key sk_id_curr"
        crs.bureauConsumer.bLoop -> crs.jaeger "Exports spans external_bureau_process" "OTLP gRPC" "Optional"

        crs.dwhConsumer.dLoop -> crs.tCdc "Consumes change events (and API messages)" "Kafka, group dwh-features-service, auto-commit"
        crs.dwhConsumer.dLoop -> crs.dwhConsumer.dExtract "Extracts sk_id_curr" "In-process call"
        crs.dwhConsumer.dLoop -> crs.dwhConsumer.dFlatten "Builds flat record (20 concurrent)" "In-process call"
        crs.dwhConsumer.dFlatten -> crs.dwhConsumer.dClient "fetch_all_by_sk_id_curr, get_table_columns" "In-process call"
        crs.dwhConsumer.dClient -> crs.chMart "SELECT * FROM mart_* WHERE SK_ID_CURR = ?" "ClickHouse HTTP :8123"
        crs.dwhConsumer.dLoop -> crs.tDwh "Publishes flat mart record" "Kafka, key sk_id_curr"
        crs.dwhConsumer.dLoop -> crs.jaeger "Exports spans dwh_features_process" "OTLP gRPC" "Optional"

        # ==================================================================
        # Relationships — warehouse
        # ==================================================================
        engineer -> crs.chLoader "make k8s-load-dwh (minikube mount ./data -> /mnt/data)" "kubectl"
        crs.chLoader -> kaggle "Reads CSV files from the mounted data/ folder" "File (hostPath mount)"
        crs.chLoader -> crs.chDwh "Creates tables, streams internal CSVs" "clickhouse-client native"
        crs.chLoader -> crs.chExternal "Creates tables, streams bureau / external CSVs" "clickhouse-client native"
        crs.dbt.stg -> crs.chDwh "Selects raw tables" "dbt-clickhouse"
        crs.dbt.marts -> crs.dbt.stg "ref()" "In-process call"
        crs.dbt.marts -> crs.chExternal "Selects bureau, bureau_balance for mart_bureau_features" "dbt-clickhouse"
        crs.dbt.marts -> crs.chMart "CREATE TABLE AS mart_* (materialized=table)" "dbt-clickhouse"

        # ==================================================================
        # Relationships — feature platform
        # ==================================================================
        crs.feastApply -> crs.kafka "Samples topics to infer feature schemas" "kafka-python (generate_schemas_from_kafka.py)"
        crs.feastApply -> crs.servingStore "Writes registry.db (entities, stream feature views, feature service)" "S3 API"
        crs.feastStream.fConsumers -> crs.tAppFeatures "Consumes" "Kafka, group feast-materializer-application, latest, auto-commit"
        crs.feastStream.fConsumers -> crs.tExt "Consumes" "Kafka, group feast-materializer-external"
        crs.feastStream.fConsumers -> crs.tDwh "Consumes" "Kafka, group feast-materializer-dwh"
        crs.feastStream.fConsumers -> crs.feastStream.fBuffers "Queues (sk_id_curr, source, features)" "ThreadPoolExecutor(20)"
        crs.feastStream.fBuffers -> crs.feastStream.fWriter "Flushes batch (<=200 rows / 300 ms)" "In-process call"
        crs.feastStream.fWriter -> crs.feastStream.fCoord "Per row, after a successful batch write" "In-process call"
        crs.feastStream.fCoord -> crs.feastStream.fReady "count == 3" "In-process call"
        crs.feastStream.fWriter -> crs.redis "write_to_online_store (DB 0)" "Redis protocol"
        crs.feastStream.fWriter -> crs.servingStore "Loads and refreshes registry.db" "S3 API"
        crs.feastStream.fCoord -> crs.redis "EVALSHA SADD/EXPIRE/SCARD feature_coordination:<id> (DB 1)" "Redis Lua"
        crs.feastStream.fReady -> crs.tReady "Publishes readiness event" "Kafka, key sk_id_curr"

        # ==================================================================
        # Relationships — scoring
        # ==================================================================
        crs.kafkaSource -> crs.tReady "Consumes" "Kafka, group knative-scoring-consumer, 8 consumers"
        crs.kafkaSource -> crs.sequence "Delivers CloudEvent (retry 3, exp 1 s)" "HTTP CloudEvents"
        crs.kafkaSource -> crs.dlqSink "Dead-letters undeliverable events" "HTTP CloudEvents"
        crs.sequence -> crs.scoring.sRoutes "POST /v1/score-by-id via KafkaChannel dispatcher (retry 3)" "HTTP CloudEvents via Kourier, activator, queue-proxy -> :3000"
        crs.sequence -> crs.outputSink "Forwards step reply" "HTTP CloudEvents"
        crs.sequence -> crs.dlqSink "Dead-letters failed step deliveries" "HTTP CloudEvents"
        crs.outputSink -> crs.tScoring "Produces decision" "Kafka, binary content mode"
        crs.dlqSink -> crs.tDlq "Produces failed event" "Kafka, binary content mode"
        decisionConsumer -> crs.tScoring "Should consume decisions (missing)" "Kafka" "Gap"

        crs.scoring.sRoutes -> crs.scoring.sLoader "ensure_model_loaded()" "In-process call"
        crs.scoring.sRoutes -> crs.scoring.sFeast "_fetch_features_from_feast(sk_id_curr)" "In-process call"
        crs.scoring.sFeast -> crs.scoring.sMapper "Maps result to model columns" "In-process call"
        crs.scoring.sRoutes -> crs.scoring.sPredict "_predict_and_create_response()" "In-process call"
        crs.scoring.sPredict -> crs.scoring.sMapper "Builds one-row DataFrame in signature order" "In-process call"
        crs.scoring.sRoutes -> crs.scoring.sEvent "Wraps result / under-review" "In-process call"
        crs.scoring.sRoutes -> crs.scoring.sTiming "Logs timings" "In-process call"
        crs.scoring.sFeast -> crs.redis "get_online_features (DB 0)" "Redis protocol"
        crs.scoring.sFeast -> crs.servingStore "Loads registry.db (per request)" "S3 API"
        crs.scoring.sLoader -> crs.servingStore "Resolves stream feature views at startup" "S3 API (registry.db)"
        crs.scoring.sTiming -> crs.jaeger "Exports spans" "OTLP gRPC" "Optional"

        # ==================================================================
        # Relationships — model lifecycle
        # ==================================================================
        scientist -> crs.workstationTraining "Runs notebooks, model_pipeline.py, train_register.py" "Terminal / Jupyter"
        scientist -> crs.mlflow "Compares runs, transitions a version to Production" "MLflow UI / client, port-forward :5000"
        scientist -> crs.kfp "Uploads and runs the training pipeline" "KFP UI / SDK"
        crs.workstationTraining -> kaggle "Reads raw CSVs and data/complete_feature_dataset.csv" "File"
        crs.workstationTraining -> crs.mlflow "Logs params, metrics, model, feast_metadata.yaml; registers credit_risk_model" "MLflow REST"
        crs.workstationTraining -> crs.mlflowArtifacts "Uploads artifacts" "S3 API (MLFLOW_S3_ENDPOINT_URL)"

        engineer -> crs.chMart "make k8s-export-training-snapshot" "kubectl exec clickhouse-client"
        crs.chMart -> crs.trainingStore "INSERT INTO FUNCTION s3(...) CSVWithNames" "ClickHouse s3 table function"
        crs.kfp.kFetch -> crs.trainingStore "Downloads snapshot CSV" "S3 API (boto3)"
        crs.kfp.kFetch -> crs.kfp.kRay "Dataset artifact" "In-process call"
        crs.kfp.kRay -> crs.ray "Submits trials" "Ray client (ray://)"
        crs.kfp.kRay -> crs.kfp.kTrain "best_params_json" "In-process call"
        crs.kfp.kTrain -> crs.mlflow "Logs run, registers, transitions stage" "MLflow REST"
        crs.kfp.kTrain -> crs.mlflowArtifacts "Uploads model + feast_metadata.yaml" "S3 API"

        crs.mlflow -> crs.mlflowDb "Reads/writes runs and registry" "PostgreSQL"
        crs.mlflow -> crs.mlflowArtifacts "Serves / proxies artifacts" "S3 API"
        crs.mlflowWatcher -> crs.mlflow "Polls Production version every 10 s" "MLflow REST"
        crs.mlflowWatcher -> crs.bentoBuilder "Creates Job with MODEL_URI, VERSION_TAG" "Kubernetes API (batch/v1 Job)"
        crs.bentoBuilder -> github "git clone APP_REPO@APP_REF (application/scoring)" "HTTPS"
        crs.bentoBuilder -> crs.mlflow "Loads promoted model" "MLflow REST"
        crs.bentoBuilder -> crs.mlflowArtifacts "Downloads model artifacts" "S3 API"
        crs.bentoBuilder -> crs.servingStore "Uploads Bento to bentoml-bundles/bentos/credit_risk_model/vN/" "S3 API"
        crs.servingWatcher -> crs.servingStore "Lists and downloads Bentos every 30 s" "S3 API (boto3)"
        crs.servingWatcher -> crs.imageRegistry "Pushes credit-risk-scoring:vN" "Docker registry API (DinD)"
        crs.servingWatcher -> crs.scoring "Creates / patches / deletes InferenceService credit-risk-vN" "Kubernetes API (serving.kserve.io/v1beta1)"
        crs.servingWatcher -> crs.sequence "Patches step ref to the newest ISVC" "Kubernetes API (flows.knative.dev/v1)"
        crs.scoring -> crs.imageRegistry "Image pulled by kubelet" "Docker registry API"

        # ==================================================================
        # Relationships — operations, observability, tests
        # ==================================================================
        engineer -> crs "make k8s-* targets, port-forwards, kubectl" "kubectl, Helm, Makefile"
        engineer -> crs.grafana "Reads dashboards" "Web browser, port-forward"
        engineer -> crs.elastic "Searches logs (Kibana)" "Kibana in a web browser"
        engineer -> crs.kafkaUi "Inspects topics and lag" "port-forward :8080"
        engineer -> crs.loadTest "Runs run_e2e_load_test.sh" "bash, Locust"
        engineer -> github "Pushes code" "git over HTTPS"
        crs.grafana -> crs.prometheus "PromQL" "HTTP"
        crs.elastic -> crs.api "Collects container stdout (loguru JSON)" "Filebeat DaemonSet"
        crs.elastic -> crs.bureauConsumer "Collects container stdout (loguru JSON)" "Filebeat DaemonSet"
        crs.elastic -> crs.dwhConsumer "Collects container stdout (loguru JSON)" "Filebeat DaemonSet"
        crs.elastic -> crs.feastStream "Collects container stdout (loguru JSON)" "Filebeat DaemonSet"
        crs.elastic -> crs.scoring "Collects container stdout (loguru JSON)" "Filebeat DaemonSet"
        crs -> registries "Pulls public and ngnquanq/* images" "HTTPS"

        crs.loadTest -> crs.pgbouncer "INSERT INTO loan_applications (bypasses the API)" "PostgreSQL :6432"
        crs.loadTest -> crs.tScoring "Correlates decisions per worker consumer group" "Kafka"
        crs.loadTest -> crs.tDlq "Counts failures" "Kafka"

        # ==================================================================
        # Relationships — PLANNED (target design; tag Planned)
        # ==================================================================
        crs.api.routes -> crs.api.apiKeyGuard "Every /api/v1 request passes through" "FastAPI Depends" "Planned"
        crs.frontend -> crs.api.apiKeyGuard "Sends X-API-Key" "HTTP header" "Planned"
        crs.feastStream.fWriter -> crs.feastStream.readiness "register_arrival(id, group) after each batch write" "In-process call" "Planned"
        crs.feastStream.readiness -> crs.redis "SADD/EXPIRE + SET dispatched NX (DB 1)" "Redis Lua" "Planned"
        crs.feastStream.readiness -> crs.tReady "Publishes once per application" "Kafka" "Planned"
        crs.feastStream.readiness -> crs.tTimeout "Publishes for expired partial sets" "Kafka" "Planned"
        crs.scoring.sRoutes -> crs.scoring.sPolicy "decide(score)" "In-process call" "Planned"
        crs.decisionRecorder -> crs.tScoring "Consumes decisions" "Kafka, group decision-recorder, manual commit" "Planned"
        crs.decisionRecorder -> crs.tTimeout "Consumes timeouts" "Kafka, group decision-recorder" "Planned"
        crs.decisionRecorder -> crs.opsDb "INSERT application_status_log ON CONFLICT (event_id) DO NOTHING" "asyncpg" "Planned"
        crs.flink -> crs.featureCatalog "Sink column list generated from" "build-time" "Planned"
        crs.feastApply -> crs.featureCatalog "Feature view schemas generated from" "build-time" "Planned"
        crs.scoring.sLoader -> crs.featureCatalog "Validates model features against" "import" "Planned"
        crs.trainingRecipe -> crs.featureCatalog "Selects model features (excludes protected)" "import" "Planned"
        crs.workstationTraining -> crs.trainingRecipe "Calls fit/evaluate/register" "import" "Planned"
        crs.kfp.kTrain -> crs.trainingRecipe "Calls fit/evaluate/register" "import" "Planned"
        crs.trainingRecipe -> crs.mlflow "Logs metrics, dir_gender, model_card.md, tags git_commit/data_snapshot_id/catalog_version" "MLflow REST" "Planned"

        # ==================================================================
        # Deployment — as run from the Makefile
        # ==================================================================
        minikube = deploymentEnvironment "Minikube" {
            ws = deploymentNode "Developer workstation" "32 GB RAM minimum, holds data/ CSVs and runs notebooks + Locust." "macOS / Linux" {
                deploymentNode "Python environment" "conda env dataEngineer-env / venv" "Python 3.10+" {
                    containerInstance crs.workstationTraining
                    containerInstance crs.loadTest
                }
                mk = deploymentNode "Minikube profile mlops" "make k8s-up: 20 CPU, 24 GB RAM, 80 GB disk; addons ingress, metallb, metrics-server." "Minikube, Docker driver, Kubernetes v1.28.3" {
                    metricsServer = infrastructureNode "metrics-server" "Feeds HPAs (bureau, feature, feast-stream, MLflow)." "Kubernetes addon"
                    metallb = infrastructureNode "MetalLB" "LoadBalancer IPs for MinIO consoles." "Kubernetes addon"

                    nsIngress = deploymentNode "ns ingress-nginx" "Minikube ingress addon" "Namespace" {
                        ingressCtl = infrastructureNode "ingress-nginx controller" "Serves Ingresses api-gateway and frontend-ingress." "NGINX"
                        ingressI = containerInstance crs.ingress
                    }
                    deploymentNode "ns api-gateway" "Public entry: UI and API" "Namespace" {
                        deploymentNode "api-service" "Service api-service :80 -> 8000" "Deployment" "" 2 {
                            containerInstance crs.api
                        }
                        deploymentNode "frontend-service" "Service frontend-service :8501" "Deployment" {
                            containerInstance crs.frontend
                        }
                    }
                    nsData = deploymentNode "ns data-services" "Operational data, streaming and warehouse" "Namespace" {
                        deploymentNode "ops-postgres-0" "PVC-backed" "StatefulSet" {
                            containerInstance crs.opsDb
                        }
                        deploymentNode "ops-pgbouncer" "Service :6432" "Deployment" {
                            containerInstance crs.pgbouncer
                        }
                        deploymentNode "data-minio-server" "Service :9000, bucket loan-documents" "Deployment" {
                            containerInstance crs.docStore
                        }
                        deploymentNode "kafka-broker-0" "Single KRaft node; every topic lives here." "StatefulSet" {
                            containerInstance crs.kafka
                            containerInstance crs.tCdc
                            containerInstance crs.tAppFeatures
                            containerInstance crs.tExtRaw
                            containerInstance crs.tExt
                            containerInstance crs.tDwh
                            containerInstance crs.tReady
                            containerInstance crs.tScoring
                            containerInstance crs.tDlq
                        }
                        deploymentNode "schema-registry" "Service :8081" "Deployment" {
                            containerInstance crs.schemaRegistry
                        }
                        deploymentNode "kafka-ui" "Service :8080" "Deployment" {
                            containerInstance crs.kafkaUi
                        }
                        deploymentNode "debezium-connect" "+ init container registering the connector" "Deployment" {
                            containerInstance crs.debezium
                        }
                        deploymentNode "flink-jobmanager + flink-taskmanager x2" "8 task slots per TaskManager; jobs submitted by Jobs flink-submit-cdc / flink-submit-bureau" "Deployments" {
                            containerInstance crs.flink
                        }
                        bureauDep = deploymentNode "bureau-consumer" "HPA min 2 max 6 @70% CPU; requests 250m, limits 2 CPU" "Deployment" "" 2 {
                            bureauI = containerInstance crs.bureauConsumer
                        }
                        dwhDep = deploymentNode "feature-consumer" "HPA min 2 max 6 @70% CPU; requests 250m, limits 2 CPU" "Deployment" "" 2 {
                            dwhI = containerInstance crs.dwhConsumer
                        }
                        deploymentNode "clickhouse-server-0" "CPU request 2, limit 4 (raised after load test cycle 0)" "StatefulSet" {
                            containerInstance crs.chExternal
                            containerInstance crs.chDwh
                            containerInstance crs.chMart
                        }
                        deploymentNode "Batch jobs" "Run on demand by make k8s-load-dwh / k8s-core" "Jobs" {
                            containerInstance crs.chLoader
                            containerInstance crs.dbt
                        }
                    }
                    nsFeast = deploymentNode "ns feature-registry" "Feast and Redis" "Namespace" {
                        deploymentNode "feast-redis" "Service :6379, no persistence" "Deployment" {
                            containerInstance crs.redis
                        }
                        feastDep = deploymentNode "feast-stream" "HPA min 2 max 6" "Deployment" "" 2 {
                            feastI = containerInstance crs.feastStream
                        }
                        deploymentNode "feast-apply" "Run on deploy and on schema change" "Job" {
                            containerInstance crs.feastApply
                        }
                    }
                    nsKnative = deploymentNode "ns knative-serving / knative-eventing / kourier-system" "Knative control and data plane" "Namespaces" {
                        knServing = infrastructureNode "Knative Serving controllers" "activator, autoscaler, controller, net-kourier-controller." "Knative Serving"
                        knEventing = infrastructureNode "Knative Eventing + Kafka controllers" "eventing-controller, kafka-controller, kafka-source-dispatcher, kafka-channel-dispatcher (1 replica; scaling to 4 caused rebalancing storms), kafka-sink-receiver." "Knative Eventing 1.13 + eventing-kafka"
                    }
                    nsKserve = deploymentNode "ns kserve" "Eventing resources and InferenceServices" "Namespace" {
                        kserveCtl = infrastructureNode "kserve-controller-manager" "Reconciles InferenceServices (serverless mode, via Knative Serving)." "KServe"
                        kafkaSourceI = containerInstance crs.kafkaSource
                        sequenceI = containerInstance crs.sequence
                        outSinkI = containerInstance crs.outputSink
                        dlqSinkI = containerInstance crs.dlqSink
                        predictor = deploymentNode "credit-risk-vN-predictor" "Knative revision: KPA concurrency target 1, containerConcurrency 1, min 3 / max 10 pods, scale-down delay 60 s; requests 500m / 512Mi, limits 2 CPU / 1Gi" "InferenceService (KServe serverless)" "" 3 {
                            queueProxy = infrastructureNode "queue-proxy" "Knative sidecar in every predictor pod; logged connection resets to 127.0.0.1:3000 under load." "Sidecar"
                            scoringI = containerInstance crs.scoring
                        }
                    }
                    nsServing = deploymentNode "ns model-serving" "Bento storage, image build and registry" "Namespace" {
                        servingMinio = deploymentNode "serving-minio" "+ serving-minio-console" "Helm (MinIO)" {
                            servingStoreI = containerInstance crs.servingStore
                        }
                        deploymentNode "serving-watcher" "2 containers: watcher (python:3.10-slim) + docker:dind" "Deployment" {
                            containerInstance crs.servingWatcher
                        }
                        deploymentNode "docker-registry" "Service :5000" "Deployment" {
                            containerInstance crs.imageRegistry
                        }
                    }
                    deploymentNode "ns model-registry" "MLflow and promotion automation" "Namespace" {
                        deploymentNode "mlflow" "Service :80, port-forward :5000" "Helm (community chart)" {
                            containerInstance crs.mlflow
                        }
                        deploymentNode "mlflow-postgresql-0" "MLflow backend store" "StatefulSet" {
                            containerInstance crs.mlflowDb
                        }
                        deploymentNode "mlflow-minio" "MLflow artifact store" "Helm (MinIO)" {
                            containerInstance crs.mlflowArtifacts
                        }
                        deploymentNode "mlflow-watcher" "Polls every 10 s" "Deployment" {
                            containerInstance crs.mlflowWatcher
                        }
                        deploymentNode "bento-builder-vN" "Created per promotion" "Job" {
                            containerInstance crs.bentoBuilder
                        }
                    }
                    nsTraining = deploymentNode "ns training-data" "Training snapshots" "Namespace" {
                        trainingMinio = deploymentNode "training-minio" "+ console" "Helm (MinIO)" {
                            trainingStoreI = containerInstance crs.trainingStore
                        }
                    }
                    deploymentNode "ns kubeflow" "~15 images on first pull" "Namespace" {
                        deploymentNode "Kubeflow Pipelines 2.14.3" "ml-pipeline, Argo workflow controller, metadata, minio" "Kustomize manifests" {
                            containerInstance crs.kfp
                        }
                    }
                    nsRay = deploymentNode "ns ray" "KubeRay" "Namespace" {
                        kuberay = infrastructureNode "kuberay-operator" "Manages RayCluster CRDs." "KubeRay"
                        rayc = deploymentNode "raycluster-k8s" "1 head + 2 workers" "RayCluster" {
                            rayI = containerInstance crs.ray
                        }
                    }
                    deploymentNode "ns monitoring" "Metrics" "Namespace" {
                        deploymentNode "kube-prometheus-stack" "Prometheus, Grafana, exporters" "Helm" {
                            containerInstance crs.prometheus
                            containerInstance crs.grafana
                        }
                    }
                    deploymentNode "ns logging" "Often Pending on small machines" "Namespace" {
                        deploymentNode "ECK stack" "elastic-operator-0, elasticsearch-es-default-0, Kibana, Filebeat DaemonSet" "ECK operator" {
                            containerInstance crs.elastic
                        }
                    }
                    deploymentNode "ns tracing (not deployed by Makefile)" "Chart in platform/ops/k8s/tracing" "Namespace" "Optional" {
                        deploymentNode "jaeger" "NodePorts 30317 / 30318 / 30686" "Helm" {
                            containerInstance crs.jaeger
                        }
                    }
                }
            }

            # Infrastructure relationships
            minikube.ws.mk.nsIngress.ingressCtl -> minikube.ws.mk.nsIngress.ingressI "Implements Ingress rules" "NGINX"
            minikube.ws.mk.metricsServer -> minikube.ws.mk.nsData.bureauDep.bureauI "CPU metrics for HPA" "metrics.k8s.io"
            minikube.ws.mk.metricsServer -> minikube.ws.mk.nsData.dwhDep.dwhI "CPU metrics for HPA" "metrics.k8s.io"
            minikube.ws.mk.metricsServer -> minikube.ws.mk.nsFeast.feastDep.feastI "CPU metrics for HPA" "metrics.k8s.io"
            minikube.ws.mk.metallb -> minikube.ws.mk.nsServing.servingMinio.servingStoreI "LoadBalancer IP for console" "L2 ARP"
            minikube.ws.mk.metallb -> minikube.ws.mk.nsTraining.trainingMinio.trainingStoreI "LoadBalancer IP for console" "L2 ARP"
            minikube.ws.mk.nsKnative.knEventing -> minikube.ws.mk.nsKserve.kafkaSourceI "kafka-source-dispatcher consumes and delivers" "Knative Eventing"
            minikube.ws.mk.nsKnative.knEventing -> minikube.ws.mk.nsKserve.sequenceI "kafka-channel-dispatcher (1 replica) delivers to the step" "Knative Eventing"
            minikube.ws.mk.nsKnative.knEventing -> minikube.ws.mk.nsKserve.outSinkI "kafka-sink-receiver produces" "Knative Eventing"
            minikube.ws.mk.nsKnative.knEventing -> minikube.ws.mk.nsKserve.dlqSinkI "kafka-sink-receiver produces" "Knative Eventing"
            minikube.ws.mk.nsKserve.kserveCtl -> minikube.ws.mk.nsKserve.predictor.scoringI "Reconciles InferenceService into a Knative Service" "KServe"
            minikube.ws.mk.nsKnative.knServing -> minikube.ws.mk.nsKserve.predictor.queueProxy "Activator buffers, autoscaler (KPA) scales on concurrency" "Knative Serving"
            minikube.ws.mk.nsKserve.predictor.queueProxy -> minikube.ws.mk.nsKserve.predictor.scoringI "Enforces containerConcurrency 1, proxies to :3000" "HTTP"
            minikube.ws.mk.nsRay.kuberay -> minikube.ws.mk.nsRay.rayc.rayI "Manages head and workers" "KubeRay"
        }
    }

    views {
        properties {
            "structurizr.sort" "key"
        }

        # ------------------------------------------------------------------
        # Level 1
        # ------------------------------------------------------------------
        systemLandscape "L0-Landscape" "Everything the platform touches." {
            include *
            autoLayout tb
        }

        systemContext crs "L1-Context" "System context: who uses the platform and what it depends on." {
            include *
            autoLayout tb
        }

        # ------------------------------------------------------------------
        # Level 2 — containers (one overview + one view per plane)
        # ------------------------------------------------------------------
        container crs "L2-All" "Every container. Dense by design; use the per-plane views to read it." {
            include *
            exclude "element.tag==Observability"
            exclude "element.tag==Test"
            exclude "element.tag==Planned"
            autoLayout tb
        }

        container crs "L2-1-Intake" "Intake: UI, API, operational store, documents and the CDC hand-off." {
            include applicant crs.ingress crs.frontend crs.api crs.opsDb crs.docStore crs.debezium crs.tCdc crs.pgbouncer crs.jaeger
            autoLayout lr
        }

        container crs "L2-2-Feature-Pipeline" "From one CDC topic to three feature topics, the online store and a readiness event." {
            include crs.debezium crs.tCdc crs.flink crs.bureauConsumer crs.dwhConsumer crs.tAppFeatures crs.tExtRaw crs.tExt crs.tDwh crs.chExternal crs.chMart crs.feastStream crs.redis crs.servingStore crs.tReady
            autoLayout tb
        }

        container crs "L2-3-Scoring" "Readiness event -> Knative -> KServe predictor -> decision topic; and who changes the predictor." {
            include crs.tReady crs.kafkaSource crs.sequence crs.scoring crs.outputSink crs.dlqSink crs.tScoring crs.tDlq crs.redis crs.servingStore crs.servingWatcher crs.imageRegistry decisionConsumer
            autoLayout tb
        }

        container crs "L2-4-Warehouse" "Batch: CSVs -> ClickHouse -> dbt marts -> training snapshot." {
            include engineer kaggle crs.chLoader crs.chDwh crs.chExternal crs.dbt crs.chMart crs.trainingStore crs.bureauConsumer crs.dwhConsumer
            autoLayout tb
        }

        container crs "L2-5-Model-Lifecycle" "Train -> register -> promote -> build -> deploy." {
            include scientist crs.workstationTraining crs.trainingStore crs.kfp crs.ray crs.mlflow crs.mlflowDb crs.mlflowArtifacts crs.mlflowWatcher crs.bentoBuilder github crs.servingStore crs.servingWatcher crs.imageRegistry crs.scoring crs.sequence crs.chMart kaggle
            autoLayout tb
        }

        container crs "L2-6-Ops" "Operations, observability and the load-test harness." {
            include engineer crs.prometheus crs.grafana crs.elastic crs.jaeger crs.kafkaUi crs.kafka crs.loadTest crs.pgbouncer crs.opsDb crs.tScoring crs.tDlq crs.api crs.bureauConsumer crs.dwhConsumer crs.scoring
            autoLayout tb
        }

        container crs "L2-7-Kafka-Topology" "Every producer and consumer of every topic." {
            include "element.tag==Topic"
            include crs.api crs.debezium crs.flink crs.bureauConsumer crs.dwhConsumer crs.feastStream crs.kafkaSource crs.outputSink crs.dlqSink crs.loadTest decisionConsumer
            exclude "element.tag==Planned"
            autoLayout tb
        }

        # ------------------------------------------------------------------
        # Level 3 — components
        # ------------------------------------------------------------------
        component crs.api "L3-API" "Clean Architecture layers inside the Loan Application API." {
            include *
            exclude "element.tag==Planned"
            autoLayout lr
        }
        component crs.flink "L3-Flink" "The two PyFlink jobs and their UDFs." {
            include *
            autoLayout tb
        }
        component crs.bureauConsumer "L3-Bureau-Service" "External bureau service internals." {
            include *
            autoLayout tb
        }
        component crs.dwhConsumer "L3-DWH-Service" "DWH features service internals." {
            include *
            autoLayout lr
        }
        component crs.feastStream "L3-Feast-Materialiser" "Micro-batching and 3-source completeness coordination." {
            include *
            exclude "element.tag==Planned"
            autoLayout lr
        }
        component crs.scoring "L3-Scoring-Service" "Inside the KServe predictor." {
            include *
            exclude "element.tag==Planned"
            autoLayout tb
        }
        component crs.kfp "L3-Training-Pipeline" "Kubeflow pipeline steps." {
            include *
            exclude "element.tag==Planned"
            autoLayout lr
        }
        component crs.dbt "L3-dbt" "dbt layers." {
            include *
            autoLayout lr
        }

        # ------------------------------------------------------------------
        # Dynamic views (sequence flows). Detailed Mermaid sequence diagrams with
        # alternatives and failure paths live in docs/architecture/sequences.md.
        # ------------------------------------------------------------------
        dynamic crs "D1-Submit-Application" "S1: a loan application is submitted through the UI." {
            applicant -> crs.ingress "GET / (Minikube IP)"
            crs.ingress -> crs.frontend "Proxies to frontend-service:8501"
            crs.frontend -> crs.api "POST /api/v1/applications (JSON, 24 fields)"
            crs.api -> crs.opsDb "SELECT by sk_id_curr, then INSERT (or UPDATE), COMMIT"
            crs.api -> crs.tCdc "Produce {sk_id_curr, type: APPLICATION_SUBMITTED} (dual write, unflushed)"
            crs.debezium -> crs.opsDb "Reads the committed row from the WAL (pgoutput)"
            crs.debezium -> crs.tCdc "Publishes change event op=c"
            autoLayout lr
        }

        dynamic crs "D2-Feature-Engineering" "S2: one change event fans out into three feature groups and a readiness signal. Branches A, B and C run concurrently; they are listed one after another only for numbering." {
            crs.flink -> crs.tCdc "[A applicant] CDC job reads the change event"
            crs.flink -> crs.tAppFeatures "[A applicant] Upserts applicant features (days_birth, days_employed, flags)"
            crs.feastStream -> crs.tAppFeatures "[A applicant] Consumes (group feast-materializer-application)"
            crs.bureauConsumer -> crs.tCdc "[B bureau] Reads the change event"
            crs.bureauConsumer -> crs.chExternal "[B bureau] bureau + bureau_balance + external_score lookups"
            crs.bureauConsumer -> crs.tExtRaw "[B bureau] Publishes raw bureau payload"
            crs.flink -> crs.tExtRaw "[B bureau] Bureau job reads the payload"
            crs.flink -> crs.tExt "[B bureau] Upserts ~60 BUREAU_* features"
            crs.feastStream -> crs.tExt "[B bureau] Consumes (group feast-materializer-external)"
            crs.dwhConsumer -> crs.tCdc "[C history] Reads the change event"
            crs.dwhConsumer -> crs.chMart "[C history] mart_previous_application / pos_cash / credit_card lookups"
            crs.dwhConsumer -> crs.tDwh "[C history] Publishes flat mart record"
            crs.feastStream -> crs.tDwh "[C history] Consumes (group feast-materializer-dwh)"
            crs.feastStream -> crs.redis "Batch write to DB 0, then Lua SADD/SCARD in DB 1 for each id"
            crs.feastStream -> crs.tReady "SCARD == 3 -> publish {sk_id_curr, source, ts}"
            autoLayout tb
        }

        dynamic crs "D3-Score-Application" "S3: the readiness event becomes a decision on hc.scoring." {
            crs.kafkaSource -> crs.tReady "Consumes (group knative-scoring-consumer)"
            crs.kafkaSource -> crs.sequence "POST CloudEvent into the Sequence KafkaChannel"
            crs.sequence -> crs.scoring "Channel dispatcher POST /v1/score-by-id"
            crs.scoring -> crs.servingStore "FeatureStore() loads registry.db"
            crs.scoring -> crs.redis "get_online_features(sk_id_curr) from 3 views"
            crs.sequence -> crs.outputSink "Reply (ce-type dev.knative.scoring.response)"
            crs.outputSink -> crs.tScoring "Produce decision JSON"
            crs.sequence -> crs.dlqSink "On 3 failed retries: dead letter"
            crs.dlqSink -> crs.tDlq "Produce failed event"
            autoLayout tb
        }

        dynamic crs.feastStream "D3c-Feast-Coordination" "S2 zoomed in: how the materialiser decides an application is complete." {
            crs.feastStream.fConsumers -> crs.tExt "Poll message (auto-commit)"
            crs.feastStream.fConsumers -> crs.feastStream.fBuffers "executor.submit -> queue.put"
            crs.feastStream.fBuffers -> crs.feastStream.fWriter "200 rows or 300 ms"
            crs.feastStream.fWriter -> crs.redis "write_to_online_store(external_features)"
            crs.feastStream.fWriter -> crs.feastStream.fCoord "For each row"
            crs.feastStream.fCoord -> crs.redis "EVALSHA: SADD source, EXPIRE 300, SCARD"
            crs.feastStream.fCoord -> crs.feastStream.fReady "SCARD == 3"
            crs.feastStream.fReady -> crs.tReady "send(hc.feature_ready)"
            autoLayout lr
        }

        dynamic crs.scoring "D3s-Scoring-Request" "S3 zoomed in: one /v1/score-by-id request inside the predictor." {
            crs.sequence -> crs.scoring.sRoutes "POST /v1/score-by-id (CloudEvent)"
            crs.scoring.sRoutes -> crs.scoring.sLoader "ensure_model_loaded() (no-op after first call)"
            crs.scoring.sRoutes -> crs.scoring.sFeast "Fetch features"
            crs.scoring.sFeast -> crs.servingStore "Load registry (new FeatureStore)"
            crs.scoring.sFeast -> crs.redis "get_online_features"
            crs.scoring.sFeast -> crs.scoring.sMapper "Map to model columns"
            crs.scoring.sRoutes -> crs.scoring.sPredict "predict_proba, threshold 0.3"
            crs.scoring.sRoutes -> crs.scoring.sEvent "CloudEvent response"
            crs.scoring.sRoutes -> crs.scoring.sTiming "score_by_id_timing log"
            autoLayout tb
        }

        dynamic crs.api "D1a-API-Submission" "S1 zoomed in: the request path through the Clean Architecture layers." {
            crs.frontend -> crs.api.routes "POST /api/v1/applications"
            crs.api.routes -> crs.api.deps "Depends(get_submit_loan_workflow)"
            crs.api.deps -> crs.api.scoringGateway "KafkaScoringGateway() (new Producer)"
            crs.api.routes -> crs.api.workflow "execute(SubmitLoanInput)"
            crs.api.workflow -> crs.api.domain "LoanApplication(..., status SUBMITTED)"
            crs.api.workflow -> crs.api.repo "save()"
            crs.api.repo -> crs.api.persistenceModels "Map + flatten document_ids"
            crs.api.persistenceModels -> crs.opsDb "SELECT, INSERT, COMMIT"
            crs.api.workflow -> crs.api.scoringGateway "publish_for_scoring()"
            crs.api.scoringGateway -> crs.tCdc "produce + poll(0); errors swallowed"
            autoLayout lr
        }

        dynamic crs "D4-Upload-Document" "S4: an applicant document is uploaded with a presigned URL." {
            crs.frontend -> crs.api "POST /api/v1/presigned-url {sk_id_curr, document_type, file_extension}"
            crs.api -> crs.docStore "presigned_put_object(loan-documents, {sk}/{folder}/doc_<uuid>.<ext>)"
            crs.frontend -> crs.docStore "PUT file bytes to the presigned URL"
            crs.frontend -> crs.api "POST /api/v1/applications with document_ids"
            crs.api -> crs.opsDb "document_id_N columns stored -> flag_document_N downstream"
            autoLayout lr
        }

        dynamic crs "D5-Warehouse-Bootstrap" "S5: CSVs become marts and a training snapshot (make k8s-load-dwh, k8s-dbt, k8s-export-training-snapshot)." {
            engineer -> crs.chLoader "make k8s-load-dwh"
            crs.chLoader -> kaggle "Read CSVs from /mnt/data"
            crs.chLoader -> crs.chDwh "CREATE + INSERT internal tables"
            crs.chLoader -> crs.chExternal "CREATE + INSERT bureau, bureau_balance, external_score"
            crs.dbt -> crs.chDwh "Staging views"
            crs.dbt -> crs.chExternal "Bureau source for mart_bureau_features"
            crs.dbt -> crs.chMart "CREATE TABLE mart_*"
            engineer -> crs.chMart "make k8s-export-training-snapshot"
            crs.chMart -> crs.trainingStore "INSERT INTO FUNCTION s3(... loan_applications.csv)"
            autoLayout lr
        }

        dynamic crs "D6-Train-and-Register" "S6: both training paths end in the MLflow registry." {
            scientist -> crs.workstationTraining "model_pipeline.py -> best_model_config.json, then train_register.py --config"
            crs.workstationTraining -> kaggle "Read complete_feature_dataset.csv"
            crs.workstationTraining -> crs.mlflow "Log run, register credit_risk_model (optionally --stage Production)"
            scientist -> crs.kfp "Run training pipeline"
            crs.kfp -> crs.trainingStore "fetch_minio_snapshot"
            crs.kfp -> crs.ray "ray_tune_hyperparams (ASHA)"
            crs.kfp -> crs.mlflow "train_and_register (bootstrap CIs)"
            crs.mlflow -> crs.mlflowArtifacts "Store model + feast_metadata.yaml"
            crs.mlflow -> crs.mlflowDb "Store run + model version"
            autoLayout lr
        }

        dynamic crs "D7-Promote-to-Serving" "S7: promoting a model version to Production rolls out a new predictor with no manual step." {
            scientist -> crs.mlflow "Transition version N -> Production"
            crs.mlflowWatcher -> crs.mlflow "Poll (10 s) detects new Production version"
            crs.mlflowWatcher -> crs.bentoBuilder "Create Job bento-builder (MODEL_URI, VERSION_TAG=vN)"
            crs.bentoBuilder -> github "git clone application/scoring"
            crs.bentoBuilder -> crs.mlflow "Load model"
            crs.bentoBuilder -> crs.servingStore "Upload Bento vN"
            crs.servingWatcher -> crs.servingStore "Poll (30 s) finds vN, downloads it"
            crs.servingWatcher -> crs.imageRegistry "docker build + push credit-risk-scoring:vN"
            crs.servingWatcher -> crs.scoring "Create InferenceService credit-risk-vN"
            crs.servingWatcher -> crs.sequence "Patch Sequence step -> credit-risk-vN"
            crs.scoring -> crs.servingStore "Startup: resolve feature views in registry.db"
            autoLayout tb
        }

        dynamic crs "D8-Load-Test" "S8: how tests/test_load measures end-to-end latency (bypasses the API)." {
            engineer -> crs.loadTest "USERS=10 SPAWN_RATE=2 RUN_TIME=3m run_e2e_load_test.sh"
            crs.loadTest -> crs.pgbouncer "INSERT loan_applications (29 RPS measured)"
            crs.pgbouncer -> crs.opsDb "Pooled session"
            crs.debezium -> crs.opsDb "CDC as in S1-S3"
            crs.loadTest -> crs.tScoring "Match decisions by sk_id_curr (17.5% within window)"
            crs.loadTest -> crs.tDlq "Count failures (0)"
            autoLayout lr
        }

        # ------------------------------------------------------------------
        # Target views (planned elements in dashed green). One per handoff package.
        # ------------------------------------------------------------------
        container crs "T-E2-Feature-Catalog" "E2 target: one feature catalog feeds Flink, Feast, training and the scoring check." {
            include crs.featureCatalog crs.flink crs.feastApply crs.trainingRecipe crs.workstationTraining crs.kfp crs.scoring crs.tAppFeatures crs.feastStream crs.servingStore
            autoLayout tb
        }
        component crs.feastStream "T-E3-Readiness" "E3 target: readiness decided once, timeouts made explicit." {
            include *
            autoLayout lr
        }
        container crs "T-E5-Decision-Delivery" "E5 target: decisions and timeouts are recorded and readable through the API." {
            include applicant crs.ingress crs.frontend crs.api crs.opsDb crs.decisionRecorder crs.tScoring crs.tTimeout crs.outputSink crs.sequence crs.scoring crs.feastStream
            autoLayout tb
        }
        component crs.scoring "T-E5-Scoring-Policy" "E5 target: the scoring service applies the decision policy." {
            include *
            autoLayout tb
        }
        container crs "T-E6-Governed-Model" "E6 target: one training recipe, catalog-checked features, fairness and lineage logged to MLflow." {
            include scientist crs.workstationTraining crs.kfp crs.trainingRecipe crs.featureCatalog crs.mlflow crs.mlflowArtifacts crs.mlflowWatcher crs.bentoBuilder crs.scoring github
            autoLayout tb
        }
        component crs.api "T-E9-API-Security" "E9 target: API key guard on every versioned application route." {
            include *
            autoLayout lr
        }
        dynamic crs "T-E5-Decision-Flow" "E5 target flow: from readiness to a status the applicant can read." {
            crs.feastStream -> crs.tReady "Publish feature_ready once (E3)"
            crs.sequence -> crs.scoring "POST /v1/score-by-id"
            crs.sequence -> crs.outputSink "Decision event (band, score, reasons, versions)"
            crs.outputSink -> crs.tScoring "Produce"
            crs.decisionRecorder -> crs.tScoring "Consume (manual commit)"
            crs.decisionRecorder -> crs.opsDb "Insert status row (idempotent)"
            crs.frontend -> crs.api "GET /api/v1/applications/{id}/status"
            crs.api -> crs.opsDb "Read latest status row"
            autoLayout tb
        }

        # ------------------------------------------------------------------
        # Deployment
        # ------------------------------------------------------------------
        deployment crs minikube "Deploy-Minikube-All" "Single-node Minikube, every namespace the Makefile creates." {
            include *
            autoLayout tb
        }
        deployment crs minikube "Deploy-Minikube-RealTime" "Only the request path: intake -> CDC -> features -> scoring." {
            include crs.ingress crs.frontend crs.api crs.opsDb crs.debezium crs.kafka crs.tCdc crs.tAppFeatures crs.tExtRaw crs.tExt crs.tDwh crs.tReady crs.tScoring crs.tDlq crs.flink crs.bureauConsumer crs.dwhConsumer crs.chExternal crs.chMart crs.feastStream crs.redis crs.kafkaSource crs.sequence crs.scoring crs.outputSink crs.dlqSink crs.servingStore
            autoLayout tb
        }

        # ------------------------------------------------------------------
        # Styles
        # ------------------------------------------------------------------
        styles {
            element "Element" {
                color #ffffff
                fontSize 22
            }
            element "Person" {
                shape person
                background #08427b
            }
            element "Software System" {
                background #1168bd
            }
            element "External" {
                background #8c8c8c
            }
            element "Container" {
                background #438dd5
            }
            element "Component" {
                background #85bbf0
                color #000000
            }
            element "Web" {
                shape WebBrowser
            }
            element "Database" {
                shape cylinder
                background #2e7d5b
            }
            element "Storage" {
                shape folder
                background #2e7d5b
            }
            element "Topic" {
                shape pipe
                background #d9822b
            }
            element "Eventing" {
                shape hexagon
                background #7a4fb3
            }
            element "Controller" {
                shape robot
                background #5b6770
            }
            element "Job" {
                shape box
                background #5b6770
            }
            element "Infra" {
                background #5b6770
            }
            element "Tool" {
                background #5b6770
            }
            element "Workstation" {
                shape component
                background #6b5b95
            }
            element "Compute" {
                background #6b5b95
            }
            element "Observability" {
                background #3a6b35
            }
            element "Test" {
                background #8a6d3b
            }
            element "Optional" {
                border dashed
                opacity 70
            }
            element "Unused" {
                border dashed
                opacity 50
            }
            element "Risk" {
                stroke #d62728
                strokeWidth 6
            }
            element "Planned" {
                stroke #2e7d32
                strokeWidth 6
                border dashed
            }
            element "Library" {
                shape component
            }
            element "Gap" {
                background #ffffff
                color #d62728
                stroke #d62728
                border dashed
            }
            element "Deployment Node" {
                color #000000
            }
            element "Infrastructure Node" {
                background #e6e6e6
                color #000000
            }
            relationship "Relationship" {
                fontSize 20
            }
            relationship "Risk" {
                color #d62728
                thickness 4
            }
            relationship "Gap" {
                color #d62728
                style dashed
            }
            relationship "Planned" {
                color #2e7d32
                style dashed
                thickness 3
            }
            relationship "Optional" {
                style dotted
                color #888888
            }
        }
    }

    configuration {
        scope softwaresystem
    }
}
