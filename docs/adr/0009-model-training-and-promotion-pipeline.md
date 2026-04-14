# ADR-0009: Automated Model Training and Promotion-to-Production Pipeline

## Status

Accepted

## Date

2026-03-22

## Context

The credit risk model must move from training through to production serving with minimal manual intervention. The pipeline involves multiple concerns — reproducible training, model versioning, artifact packaging, container image building, and serverless deployment — each handled by a dedicated service. Without a documented lifecycle, these services appear disconnected, making it difficult to debug promotion failures or understand the blast radius of changes.

This ADR documents the end-to-end model lifecycle and the architectural decisions behind each service in the chain.

## Decision

### Pipeline Overview

The model lifecycle is a 7-phase automated pipeline triggered by a single manual action: promoting a model version to `Production` stage in MLflow.

```
train_register.py ──► MLflow Registry (Staging)
                            │
                      [Manual Promote to Production]
                            │
                      MLflow Watcher (polls 10s)
                            │
                      Bento Builder Job
                            │
                      MinIO (s3://bentoml-bundles)
                            │
                      Serving Watcher (polls 30s)
                            │
                      KServe InferenceService
                            │
                      Knative Sequence ──► hc.scoring topic
```

### Phase 1: Model Training

**Entry point:** `application/training/train_register.py`

The training script builds a sklearn `Pipeline` with:

1. **Preprocessing** via `ColumnTransformer`:
   - Categorical features (5): `SimpleImputer(most_frequent)` → `OrdinalEncoder(unknown_value=-1)`
   - Numeric features: `clip(0.001–0.999 quantiles)` → `SimpleImputer(median or constant=0)`
2. **Classifier**: XGBoost (`n_estimators=300, max_depth=4, lr=0.05, subsample=0.8`)
3. **Split**: 80/20 stratified by TARGET
4. **Metrics**: ROC-AUC (~0.77), accuracy at threshold 0.3

The complete pipeline (preprocessor + classifier) is logged to MLflow as a single artifact.

**Alternative entry:** Kubeflow Pipeline (`platform/ml/k8s/training-pipeline/pipeline.py`) for distributed training with Ray Tune hyperparameter search.

### Phase 2: MLflow Registration

**Service:** MLflow (`model-registry` namespace, port 5000)

After training, the model is registered as `credit_risk_model` in MLflow's Model Registry. Key artifacts logged:

| Artifact | Purpose |
|----------|---------|
| sklearn model | The full pipeline (preprocessor + XGBoost) |
| `feast_metadata.yaml` | Feature selection, entity key, column mapping, categorical/numerical split |
| Parameters | All XGBoost hyperparameters |
| Metrics | AUC, accuracy |
| Input example | First training row (for schema inference) |

`feast_metadata.yaml` is critical — it tells the scoring service which features to fetch from Feast and how to map Feast names (lowercase) to model column names (uppercase).

**Promotion is manual**: an operator transitions the model version from `Staging` → `Production` in the MLflow UI or API. This is the single human gate in the pipeline.

### Phase 3: MLflow Watcher (Promotion Detection)

**Service:** `mlflow-watcher` deployment in `model-registry` namespace (1 replica)

**Core idea:** A polling loop that detects when a new model version reaches the `Production` stage and triggers downstream automation.

**How it works:**
- Polls MLflow API every 10 seconds (`POLL_INTERVAL_SECS`)
- Queries for models at stage `Production`, compares version number against last-seen
- On new version: creates a Kubernetes Job in the `kserve` namespace using a ConfigMap-defined job template
- Passes `MODEL_URI` (e.g., `models:/credit_risk_model/12`) and `VERSION_TAG` (e.g., `v12`) to the job
- Has RBAC permissions to create Jobs in the `kserve` namespace

**Key files:**
- `platform/ml/k8s/mlflow-watcher/deployment.yaml` — pod + service account
- `platform/ml/k8s/mlflow-watcher/poller-configmap.yaml` — poll logic + trigger script
- `platform/ml/k8s/mlflow-watcher/builder-configmap.yaml` — job template + static config

### Phase 4: Bento Build and Upload

**Service:** One-shot Kubernetes Job in `kserve` namespace (TTL 1800s)

**Core idea:** Download the model from MLflow, package it with application code into a self-contained BentoML bundle, and upload to object storage.

**Steps:**
1. Clone the application repository (or use pre-mounted path)
2. Load model from MLflow (prefers sklearn flavor → xgboost → pyfunc)
3. Extract `feast_metadata.yaml` from MLflow artifacts
4. Serialize model to `application/scoring/bundle/model.joblib`
5. Run `bentoml build --version vN` using `application/scoring/bentofile.yaml`
6. Upload the built Bento to MinIO: `s3://bentoml-bundles/bentos/credit_risk_model/vN/`

The Bento bundle is self-contained: model weights, preprocessing pipeline, scoring service code, Feast client config, and all Python dependencies.

**Key files:**
- `platform/ml/k8s/kserve/bento-builder/build_and_upload.py` — build logic
- `application/scoring/bentofile.yaml` — BentoML build spec (service entry, deps, includes)

### Phase 5: Serving Watcher (Image Build)

**Service:** `serving-watcher` deployment in `model-serving` namespace (Docker-in-Docker)

**Core idea:** Polls MinIO for new Bento bundles, builds OCI container images, pushes to a registry, and manages the active set of deployed models.

**How it works:**
- Polls MinIO every 30 seconds for `bentos/credit_risk_model/v*` prefixes
- For each new version:
  1. Downloads Bento from MinIO
  2. Patches the Dockerfile (replaces `uv` with `pip`, pins `protobuf==5.29.0` for OpenTelemetry compatibility)
  3. Builds Docker image tagged as `credit-risk-scoring:vN`
  4. Pushes to Docker registry (internal or Docker Hub `ngnquanq/credit-risk-scoring`)
- Keeps top `MAX_ACTIVE_MODELS=2` versions deployed, deletes older ones

**Key files:**
- `platform/ml/k8s/kserve/serving-watcher/watcher.py` — reconciliation loop
- `platform/ml/k8s/kserve/serving-watcher/deployment.yaml` — DinD pod
- `platform/ml/k8s/kserve/serving-watcher/isvc-template-serverless.yaml` — InferenceService template

### Phase 6: KServe Deployment

**Service:** KServe InferenceService in `kserve` namespace

**Core idea:** Deploy the containerized model as a serverless Knative service with auto-scaling, and wire it into the event-driven scoring pipeline.

The serving watcher performs three actions per new version:

1. **Create InferenceService** from template:
   - Container: `credit-risk-scoring:vN` on port 3000 (BentoML)
   - Replicas: min=0 (scale-to-zero), max=4
   - Environment: `SCORING_MODEL_SOURCE=local`, `SCORING_MODEL_PATH=bundle/model.joblib`, Feast config, Kafka config, OTEL tracing
   - Resources: 1500m CPU, 768Mi memory

2. **Create/Update KafkaSource**:
   - Consumes from `hc.feature_ready` topic
   - Sinks to the latest InferenceService at `/v1/score-by-id`
   - Consumer group: `knative-scoring-consumer`
   - Delivery: 3 retries, exponential backoff, dead-letter sink

3. **Delete old InferenceServices** (versions beyond top 2)

**Key files:**
- `platform/ml/k8s/kserve/scoring-sequence.yaml` — Knative Sequence (InferenceService → KafkaSink)
- `platform/ml/k8s/kserve/kafka-sink.yaml` — output to `hc.scoring` topic
- `platform/ml/k8s/kserve/kafka-dlq-sink.yaml` — dead letter queue to `hc.scoring.dlq`

### Phase 7: Production Scoring

**Service:** BentoML scoring service (`application/scoring/service.py`) running inside the KServe pod

**Core idea:** A stateless inference microservice that fetches real-time features from Feast (Redis) and applies the packaged model.

**Startup sequence:**
1. Load model from `bundle/model.joblib` (serialized sklearn pipeline)
2. Read `feast_metadata.yaml` → extract expected feature names and mapping
3. Connect to Feast online store (Redis) and validate all model features exist in registered feature views
4. Set XGBoost `nthread=1` for single-sample throughput optimization

**Inference flow (event-driven via Knative):**
1. Receive CloudEvent from `hc.feature_ready` containing `sk_id_curr`
2. Fetch features from Feast Redis: `fs.get_online_features(features=[...], entity_rows=[{sk_id_curr}])`
3. Map Feast feature names → model column names (lowercase → uppercase via `feast_metadata.yaml`)
4. Build single-row DataFrame, call `model.predict_proba(X)`
5. Apply threshold: `prob >= 0.3` → reject, else approve
6. Return CloudEvent-wrapped response → Knative Sequence reply → KafkaSink → `hc.scoring` topic

If features are missing from Redis, returns `decision=under-review` with `reason=feature_data_unavailable`.

**Endpoints:**
- `POST /v1/score` — direct feature input (for testing)
- `POST /v1/score-by-id` — Feast-backed scoring (production path via Knative)
- `GET /healthz` — health check with model version info

### Services Summary

| Service | Namespace | Core Responsibility | Trigger |
|---------|-----------|-------------------|---------|
| **MLflow** | model-registry | Model versioning, artifact storage, promotion workflow | Manual (operator promotes to Production) |
| **MLflow Watcher** | model-registry | Detects Production promotion, triggers Bento build | Polls MLflow every 10s |
| **Bento Builder** | kserve (Job) | Downloads model + code, packages into Bento, uploads to MinIO | Created by MLflow Watcher |
| **Serving Watcher** | model-serving | Detects new Bento, builds Docker image, deploys InferenceService | Polls MinIO every 30s |
| **KServe InferenceService** | kserve | Serverless model serving with auto-scaling | Created by Serving Watcher |
| **Knative Sequence** | kserve | Routes `hc.feature_ready` events → scoring → `hc.scoring` output | Event-driven (Kafka) |
| **Scoring Service** | kserve (inside pod) | Fetches Feast features, runs XGBoost prediction, returns decision | HTTP from Knative |

## Alternatives Considered

| Option | Pros | Cons |
|--------|------|------|
| **Watcher-based automation (chosen)** | Fully automated after manual promote, decoupled services, each phase independently debuggable | Polling latency (~40s total), 5 services in chain, harder to trace failures |
| **Direct MLflow serving** | Simpler (MLflow serve), fewer services | No auto-scaling, no Kafka integration, no preprocessing bundling, vendor lock-in |
| **CI/CD pipeline (GitHub Actions)** | Familiar, centralized, push-based (no polling) | Requires external CI access to cluster, harder to run in air-gapped environments |
| **Single model version** | Simpler lifecycle, no version management | No rollback capability, risky deployments, no canary testing |

## Consequences

### Positive

- **Zero-touch deployment** after manual promotion — model reaches production in ~40 seconds
- **Rollback** by re-promoting an older MLflow version or manually deleting the InferenceService
- **Feature alignment validation** at startup prevents serving with missing features
- **Self-contained bundles** (model + preprocessing + deps) eliminate "works on my machine" issues
- **Multi-version support** (top 2 active) enables future canary/shadow deployments

### Negative

- **5-service chain** increases debugging surface — a failure in any service breaks the pipeline
- **Polling-based** detection adds ~40s latency (10s MLflow + 30s MinIO) vs. webhook-based alternatives
- **Docker-in-Docker** in the serving watcher is a security concern and adds resource overhead
- **feast_metadata.yaml** is a coupling point — if training changes features without updating this file, scoring breaks at startup

### Risks

- **Feast feature misalignment**: If model features change but Feast feature views are not updated, the scoring service will fail to start. Mitigation: startup validation logs explicit errors with missing feature names.
- **MinIO/registry unavailability**: If MinIO or Docker registry is down, new models cannot be deployed. Mitigation: existing InferenceService continues serving the previous version.
- **Knative cold start**: Scale-to-zero means first request after idle takes ~5-10s. Mitigation: set `minReplicas=1` for latency-sensitive deployments.
- **Coordination with Feast materialization**: The scoring service assumes features are in Redis. If the Feast stream processor is behind, predictions will return `under-review`. Monitor the `hc.feature_ready` topic lag.
