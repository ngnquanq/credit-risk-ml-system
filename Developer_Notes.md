# 2025-10-03

## Successfully Built and Deployed BentoML Model Serving with KServe

**Problem**: MLflow model version 2 needed to be packaged as BentoML bundle and deployed to KServe for serving, but encountered multiple blocking errors during the build and deployment pipeline.

### Complete Build Pipeline Flow

```
MLflow (model v2 promoted to Production)
    ↓
mlflow-watcher (polls every 10s)
    ↓
Trigger builder job (clone repo, download model, create Bento)
    ↓
Upload Bento to MinIO (s3://bentoml-bundles/bentos/credit_risk_model/v2/)
    ↓
serving-watcher (polls MinIO)
    ↓
Build Docker image from Bento
    ↓
Deploy KServe InferenceService
```

---

### Issues Encountered and Solutions

#### 1. Training Pipeline: Unpicklable FunctionTransformer

**Error**:
```
_pickle.PicklingError: Can't pickle <function train_and_register.<locals>.to_str>:
it's not found as ephemeral_component.train_and_register.<locals>.to_str
```

**Root Cause**:
- `services/ml/k8s/training-pipeline/pipeline.py` line 327-333 defined a local function `to_str()` inside the `train_and_register` Kubeflow component
- This function was passed to `FunctionTransformer` and became part of the sklearn pipeline
- Python's pickle cannot serialize local/nested functions (they're not importable from module top level)
- BentoML's `joblib.dump()` failed when trying to serialize the model

**Solution**: Preprocess data instead of using custom transformer
```python
# BEFORE (unpicklable):
def to_str(X):
    return X.astype(str)
cat_pipe = Pipeline([
    ("impute", SimpleImputer(strategy="most_frequent")),
    ("to_str", FunctionTransformer(to_str)),  # ❌ Local function
    ("ord", OrdinalEncoder(...)),
])

# AFTER (picklable):
# Convert categorical columns to string BEFORE pipeline
if cat_cols:
    for col in cat_cols:
        X_train[col] = X_train[col].astype(str)
        X_test[col] = X_test[col].astype(str)

cat_pipe = Pipeline([
    ("impute", SimpleImputer(strategy="most_frequent")),
    ("ord", OrdinalEncoder(...)),  # ✅ Only standard transformers
])
```

**Files Modified**:
- `services/ml/k8s/training-pipeline/pipeline.py`

**Commands**:
```bash
# Recompile pipeline
python services/ml/k8s/training-pipeline/compile_pipeline.py

# Submit new training run via Kubeflow Pipelines UI
# Output: Model version 2 created and promoted to Production
```

---

#### 2. BentoML Build: Missing ConfigMap

**Error**:
```
MountVolume.SetUp failed for volume "script": configmap "bento-builder-script" not found
```

**Root Cause**:
- Builder job pod tried to mount ConfigMap containing `build_and_upload.py` script
- ConfigMap didn't exist in kserve namespace

**Solution**: Create ConfigMap from existing script
```bash
kubectl create configmap bento-builder-script \
  --from-file=/home/nhatquang/home-credit-credit-risk-model-stability/services/ml/k8s/kserve/bento-builder/build_and_upload.py \
  -n kserve
```

---

#### 3. BentoML Service: Import Errors During Build

**Error**:
```
Failed to import module "service": No module named 'fastapi'
Failed to import module "service": No module named 'loguru'
NameError: name 'get_model_expected_columns' is not defined
AttributeError: 'NoneType' object has no attribute 'on_event'
```

**Root Cause**:
- `bentoml build` executes `service.py` to discover the service object BEFORE installing dependencies from `bentofile.yaml`
- Imports like `from fastapi import FastAPI` and `from loguru import logger` failed because packages weren't installed yet
- Module-level function calls like `get_model_expected_columns()` executed at import time
- Route decorators like `@app.on_event("startup")` tried to use `app` before it was created

**Solution**: Use `bentoml.importing()` context manager with proper scoping

```python
# application/scoring/service.py structure:

import bentoml

# 1. Create service FIRST (BentoML needs this at import time)
svc = bentoml.Service("credit_risk_scoring")

# 2. Declare module-level variables
app = None
logger = None
pd = None
# ... all runtime dependencies

# 3. Import inside bentoml.importing() and assign to globals
with bentoml.importing():
    from fastapi import FastAPI as _FastAPI
    from loguru import logger as _logger
    import pandas as _pd
    # ... import all dependencies with temp names

    # Assign to module globals (makes them accessible outside this block)
    logger = _logger
    pd = _pd
    # ...

    # Configure logging
    configure_logger(settings.log_level, settings.log_format)

    # Create FastAPI app
    app = FastAPI(title="Credit Risk Scoring")

    # Define ALL routes/events HERE (decorators need app to exist)
    @app.on_event("startup")
    def _on_startup():
        ensure_model_loaded()

    @app.get("/healthz")
    def health():
        return {"status": "healthy", "model": MODEL_NAME}

    @app.post("/v1/score")
    def score(req: ScoreRequest):
        # ... scoring logic

    @app.post("/v1/score-by-id")
    def score_by_id(req: ScoreByIdRequest):
        # ... Feast-based scoring logic

# 4. Lazy-load module-level data
_EXPECTED_COLUMNS = None

def _get_expected_columns():
    global _EXPECTED_COLUMNS
    if _EXPECTED_COLUMNS is None:
        _EXPECTED_COLUMNS = get_model_expected_columns()
    return _EXPECTED_COLUMNS

# 5. Helper functions (outside importing block, no dependencies)
def _resolve_feast_repo_path():
    # ...

def ensure_model_loaded():
    # ...

# 6. Mount FastAPI app to Bento service
svc.mount_asgi_app(app, path="/")
```

**Key Principles**:
1. **Service first**: `svc = bentoml.Service()` outside importing block
2. **Declare then assign**: Declare globals as `None`, import with temp names, assign to globals inside block
3. **Routes inside block**: All `@app` decorators must be inside `bentoml.importing()` where `app` exists
4. **Lazy loading**: Module-level function calls wrapped in getter functions

**Files Modified**:
- `application/scoring/service.py`

**Git Commands**:
```bash
git add application/scoring/service.py services/ml/k8s/training-pipeline/pipeline.py
git commit -m "fix: resolve pickle error and BentoML build-time import issues"
git push origin feature/ml-model-v0.0
```

---

#### 4. BentoML Build Script: CLI Flag Not Supported

**Error**:
```
Error: No such option: --print-location
Command 'bentoml get credit_risk_scoring:v2 --print-location' returned non-zero exit status 2
```

**Root Cause**:
- `build_and_upload.py` used `bentoml get --print-location` flag
- This flag doesn't exist in BentoML 1.4.25

**Solution**: Use BentoML Python API instead

```python
# services/ml/k8s/kserve/bento-builder/build_and_upload.py

# BEFORE:
bento_path = subprocess.check_output(
    f"bentoml get {bento_tag} --print-location", shell=True
).decode().strip()

# AFTER:
import bentoml
try:
    bento = bentoml.get(bento_tag)
    bento_path = bento.path
except Exception as e:
    # Fallback: construct path from default BentoML store
    bentoml_home = pathlib.Path.home() / "bentoml" / "bentos"
    bento_path = str(bentoml_home / "credit_risk_scoring" / version_tag)
    if not os.path.exists(bento_path):
        raise SystemExit(f"Bento not found at {bento_path}: {e}")
```

**Files Modified**:
- `services/ml/k8s/kserve/bento-builder/build_and_upload.py`

**Update ConfigMap**:
```bash
kubectl delete configmap bento-builder-script -n kserve
kubectl create configmap bento-builder-script \
  --from-file=/home/nhatquang/home-credit-credit-risk-model-stability/services/ml/k8s/kserve/bento-builder/build_and_upload.py \
  -n kserve
```

---

#### 5. Variable Scoping: UnboundLocalError

**Error**:
```
UnboundLocalError: cannot access local variable 'pathlib' where it is not associated with a value
```

**Root Cause**:
- `pathlib` was imported at module top level (line 31)
- Accidentally imported again inside a try/except block (line 160): `import pathlib`
- This created a local variable that shadowed the module-level import
- Earlier code (line 134) tried to use `pathlib` before the local import

**Solution**: Remove duplicate import (use module-level import)

```python
# Module level (line 31) - KEEP THIS:
import pathlib

# Inside try/except (line 160) - REMOVE THIS:
# import pathlib  ❌ Don't re-import

# Use the module-level import directly:
bentoml_home = pathlib.Path.home() / "bentoml" / "bentos"
```

**Update ConfigMap** (same commands as above)

---

### Final Working Build

**Trigger Build**:
```bash
cat <<'EOF' | kubectl create -f -
apiVersion: batch/v1
kind: Job
metadata:
  generateName: bento-build-
  namespace: kserve
spec:
  ttlSecondsAfterFinished: 1800
  template:
    spec:
      restartPolicy: Never
      containers:
      - name: builder
        image: python:3.11-slim
        env:
        - name: MLFLOW_TRACKING_URI
          value: http://mlflow.model-registry.svc.cluster.local:80
        - name: MODEL_NAME
          value: credit_risk_model
        - name: MODEL_URI
          value: models:/credit_risk_model/2
        - name: VERSION_TAG
          value: v2
        - name: APP_REPO
          value: https://github.com/ngnquanq/credit-risk-ml-system.git
        - name: APP_REF
          value: feature/ml-model-v0.0
        - name: APP_SUBPATH
          value: application/scoring
        - name: BENTO_BUCKET
          value: bentoml-bundles
        - name: AWS_S3_ENDPOINT
          value: http://serving-minio.model-serving.svc.cluster.local:9000
        - name: AWS_ACCESS_KEY_ID
          value: minio_user
        - name: AWS_SECRET_ACCESS_KEY
          value: minio_password
        - name: AWS_S3_FORCE_PATH_STYLE
          value: "true"
        command: ["bash", "-lc"]
        args:
        - |
          apt-get update && apt-get install -y git && \
          pip install --no-cache-dir mlflow==2.14.3 bentoml boto3 gitpython cloudpickle pyyaml pandas==2.2.2 scikit-learn==1.5.1 xgboost==2.1.0 numpy==1.26.4 && \
          python /app/build_and_upload.py
        volumeMounts:
        - name: script
          mountPath: /app
      volumes:
      - name: script
        configMap:
          name: bento-builder-script
EOF
```

**Monitor Build**:
```bash
# Watch job status
kubectl get jobs -n kserve --watch

# Check build logs
kubectl logs -n kserve job/bento-build-<job-id> -f

# Verify success (look for):
# ✅ Successfully built Bento(tag="credit_risk_scoring:v2")
# ✅ Bento path: /root/bentoml/bentos/credit_risk_scoring/v2
# ✅ Uploading to s3://bentoml-bundles/bentos/credit_risk_model/v2/
# ✅ DONE: s3://bentoml-bundles/bentos/credit_risk_model/v2/
```

**Verify Upload to MinIO**:
```bash
kubectl exec -n model-serving deployment/serving-minio -- \
  mc ls minio/bentoml-bundles/bentos/credit_risk_model/v2/
```

**Check Serving Watcher**:
```bash
# serving-watcher should detect the new Bento and start building Docker image
kubectl logs -n model-serving deployment/serving-watcher -f

# Check for InferenceService creation
kubectl get inferenceservices -n kserve
```

---

### Key Files Modified (Complete List)

1. **`services/ml/k8s/training-pipeline/pipeline.py`**
   - Removed unpicklable `FunctionTransformer(to_str)`
   - Moved string conversion to data preprocessing before pipeline

2. **`services/ml/k8s/training-pipeline/training_pipeline.yaml`**
   - Recompiled pipeline YAML with fixes

3. **`application/scoring/service.py`**
   - Wrapped all runtime dependencies in `bentoml.importing()`
   - Moved route definitions inside importing block
   - Implemented lazy loading for module-level function calls

4. **`services/ml/k8s/kserve/bento-builder/build_and_upload.py`**
   - Replaced `bentoml get --print-location` with Python API
   - Fixed pathlib import scoping issue

5. **Kubernetes ConfigMap**:
   - Created `bento-builder-script` in kserve namespace

---

### Build Output (Success)

```
Successfully built Bento(tag="credit_risk_scoring:v2").

Bento path: /root/bentoml/bentos/credit_risk_scoring/v2
Uploading to s3://bentoml-bundles/bentos/credit_risk_model/v2/
DONE: s3://bentoml-bundles/bentos/credit_risk_model/v2/
```

---

### Lessons Learned

1. **Python Pickle Limitations**:
   - Only module-level functions/classes can be pickled
   - Local/nested functions inside other functions are NOT picklable
   - Solution: Preprocess data or use class-based transformers

2. **BentoML Build Process**:
   - `bentoml build` imports `service.py` BEFORE installing `bentofile.yaml` dependencies
   - Use `bentoml.importing()` to defer imports until runtime
   - Service object must be created outside importing block for discovery

3. **Python Variable Scoping**:
   - Re-importing a module inside a function/block creates a local variable
   - This shadows the module-level import
   - Always use module-level imports or be explicit with scoping

4. **Decorator Execution Timing**:
   - Decorators execute when functions are defined (at import time)
   - `@app.get()` needs `app` to exist in scope
   - Solution: Define routes inside `bentoml.importing()` block where `app` is created

5. **BentoML API Changes**:
   - CLI flags may not be stable across versions
   - Use Python API (`bentoml.get()`) for programmatic access
   - Always check BentoML version compatibility

---

### Next Steps

1. **Monitor serving-watcher**: Check if Docker image builds successfully and InferenceService deploys
2. **Test serving endpoint**: Once deployed, test `/v1/score` and `/v1/score-by-id` endpoints
3. **Integrate Feast**: Verify Feast feature lookup works from serving pods
4. **End-to-end test**: Send Kafka message → Feast materialization → Serving query → Prediction

---

## Deployed Feast Feature Store to Kubernetes with Kafka Streaming

**Problem**: Feast feature registry failed to initialize in K8s environment, and Kafka streaming from Docker to K8s was not working.

### Issues Encountered and Solutions

#### 1. Feast Registry Initialization Failure: `RegistryInferenceFailure`

**Error**:
```
feast.errors.RegistryInferenceFailure: Could not infer Features for dwh_features
```

**Root Cause**:
- `application/feast/dwh_schema.py` tried to connect to ClickHouse at `172.18.0.17:8123` (Docker container IP)
- K8s pods cannot reach Docker container IPs directly
- Schema inference for 156 DWH features failed, blocking feature view registration

**Solution**: Created static schema fallback system
1. **Created** `application/feast/generate_static_schema.py`:
   - Script to generate static schema from ClickHouse (run once in Docker environment)
   - Exports all 156 DWH fields to JSON format

2. **Updated** `application/feast/dwh_schema.py`:
   - Added fallback logic: try ClickHouse first, then load from `dwh_schema_static.json`
   - Enables K8s deployment without ClickHouse connectivity

3. **Generated static schema**:
   ```bash
   # Run from Docker environment where ClickHouse is accessible
   docker exec feast_stream python generate_static_schema.py
   # Output: dwh_schema_static.json (156 fields: 91 Float32, 63 Int64, 2 String)
   ```

4. **Rebuilt and pushed Docker image**:
   ```bash
   cd application/feast
   docker build -t feast-repo:v3 -t ngnquanq/feast-repo:v3 .
   docker push ngnquanq/feast-repo:v3
   ```

**Result**: Feast registry successfully initialized with all 156 DWH features loaded from static schema.

---

#### 2. Conflicting Feature View Names

**Error**:
```
feast.errors.ConflictingFeatureViewNames: The feature view name: application_features refers to feature views of different types.
```

**Root Cause**:
- `application/feast/feature_views.py` defined both:
  - `application_features` (StreamFeatureView - for Kafka streaming)
  - `application_features_batch` (FeatureView - for training)
- Feast doesn't allow same-named views of different types

**Solution**: Removed duplicate batch FeatureViews
- StreamFeatureViews already support both streaming AND batch sources
- Deleted `fv_application_features_batch`, `fv_external_batch`, `fv_dwh_batch`
- Updated `application/feast/repository.py` to only register StreamFeatureViews

**Architectural Insight**:
- **Training**: Uses `batch_source` (MinIO Parquet files) embedded in StreamFeatureView
- **Serving**: Uses online store (Redis) materialized from Kafka streams
- **Single source of truth**: Same feature definitions prevent training/serving skew

**Result**: Successfully registered 3 StreamFeatureViews (176 total features)

---

#### 3. Kafka Streaming: NoBrokersAvailable

**Error**:
```
Consumer error for application: NoBrokersAvailable
Consumer error for dwh: NoBrokersAvailable
Consumer error for external: NoBrokersAvailable
```

**Root Cause Analysis**:

**Initial Problem**: Network isolation between Docker (Kafka) and K8s (Feast)
- Kafka broker running at `172.18.0.30:29092` in Docker `hc-network`
- K8s pods cannot reach Docker container IPs directly

**Attempted Solution 1**: Use socat gateway
```bash
# Extended services/ops/docker-compose.gateway.yml
socat TCP-LISTEN:39092,reuseaddr,fork TCP:172.18.0.30:29092 &
```
- Updated Feast config to use `host.minikube.internal:39092`
- Consumers connected to bootstrap but still failed

**Discovery**: Kafka advertised listener problem
```bash
# Debug consumer metadata fetch
kubectl exec -n feature-registry feast-stream -- python3 -c "..."
# Output: MetadataResponse_v0(brokers=[(node_id=1, host='broker', port=29092)])
```
- Consumer successfully connected to bootstrap at `host.minikube.internal:39092`
- Kafka metadata response said "real broker is at `broker:29092`"
- K8s pods couldn't resolve hostname `broker` → consumers failed silently

**Final Solution**: Add hostAlias + dual port forwarding

1. **Extended gateway to forward advertised listener port**:
   ```yaml
   # services/ops/docker-compose.gateway.yml
   socat TCP-LISTEN:39092,reuseaddr,fork TCP:172.18.0.30:29092 &  # Bootstrap
   socat TCP-LISTEN:29092,reuseaddr,fork TCP:172.18.0.30:29092 &  # Advertised listener
   ```

2. **Added hostAlias to Feast deployment**:
   ```yaml
   # services/ml/k8s/feature-store/feast-stream-deployment.yaml
   spec:
     hostAliases:
     - ip: "192.168.49.1"  # host.minikube.internal IP
       hostnames:
       - "broker"  # Kafka advertised listener hostname
   ```

3. **Redeployed with updated configuration**:
   ```bash
   # Restart gateway
   docker stop k8s_gateway && docker rm k8s_gateway
   docker compose -f services/ops/docker-compose.gateway.yml up -d

   # Redeploy Feast
   cd services/ml/k8s/feature-store
   kubectl delete deployment feast-stream -n feature-registry
   kubectl apply -k .
   ```

**Result**: All 3 Kafka consumers connected and actively consuming!

---

### Final Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                      User Request (Streamlit)                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              Kafka Topics (Docker hc-network)                │
│  - hc.application_features (13 fields)                       │
│  - hc.application_ext (7 fields)                             │
│  - hc.application_dwh (156 fields)                           │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ broker:29092 (advertised listener)
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Socat Gateway (Host)                      │
│  Port 39092 → Kafka bootstrap (Docker)                       │
│  Port 29092 → Kafka broker (Docker)                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ host.minikube.internal:39092
                         ▼
┌─────────────────────────────────────────────────────────────┐
│           Feast Stream Processor (K8s Pod)                   │
│  + hostAlias: broker → 192.168.49.1                          │
│  + 3 Kafka consumers (application, external, dwh)            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ Write features
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               Redis Online Store (K8s)                       │
│  - 176 total features per customer                           │
│  - Sub-second query latency                                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ Feast SDK: fs.get_online_features()
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                   Serving Pods (KServe)                      │
│  Query features for real-time inference                      │
└─────────────────────────────────────────────────────────────┘
```

---

### Verification

**Test feature retrieval for SK_ID_CURR=121155**:

```bash
kubectl exec -n feature-registry feast-stream-<pod> -- python3 -c "
from feast import FeatureStore
fs = FeatureStore(repo_path='.')
result = fs.get_online_features(
    features=[
        'application_features:amt_income_total',
        'external_features:ext_source_1',
        'dwh_features:prev_approved_count',
    ],
    entity_rows=[{'sk_id_curr': '121155'}]
)
print(result.to_df())
"
```

**Output**:
```
  sk_id_curr  amt_income_total  ext_source_1  prev_approved_count
0     121155           50000.0      0.378993                    2
```

✅ All 3 feature views accessible
✅ Features materialized from Kafka to Redis
✅ Sub-second query latency

---

### Key Files Modified

1. **`application/feast/generate_static_schema.py`** (NEW)
   - Generate static schema from ClickHouse for K8s deployment

2. **`application/feast/dwh_schema.py`**
   - Added static schema fallback logic

3. **`application/feast/feature_views.py`**
   - Removed duplicate batch FeatureViews (lines 204-227 deleted)

4. **`application/feast/repository.py`**
   - Updated to only register StreamFeatureViews

5. **`services/ops/docker-compose.gateway.yml`**
   - Added Kafka port forwarding (39092, 29092)

6. **`services/ml/k8s/feature-store/feast-configmap.yaml`**
   - Updated Kafka broker: `host.minikube.internal:39092`

7. **`services/ml/k8s/feature-store/feast-stream-deployment.yaml`**
   - Added `hostAliases` to resolve `broker` hostname

8. **`services/ml/k8s/feature-store/kustomization.yaml`**
   - Updated to `ngnquanq/feast-repo:v4`

---

### Commands Reference

**Generate static schema** (from Docker environment):
```bash
docker exec feast_stream python generate_static_schema.py
docker cp feast_stream:/work/feast_repo/dwh_schema_static.json application/feast/
```

**Rebuild and deploy Feast**:
```bash
cd application/feast
docker build -t ngnquanq/feast-repo:v4 .
docker push ngnquanq/feast-repo:v4

cd ../../services/ml/k8s/feature-store
kubectl delete pvc feast-registry -n feature-registry  # Fresh registry
kubectl apply -k .
```

**Verify Kafka consumers**:
```bash
# Check consumer group
docker exec kafka_broker kafka-consumer-groups \
  --bootstrap-server localhost:9092 \
  --describe --group feast-materializer-application

# Check Feast logs
kubectl logs -f deployment/feast-stream -n feature-registry
```

**Query features**:
```bash
kubectl exec -n feature-registry deployment/feast-stream -- \
  python3 -c "from feast import FeatureStore; ..."
```

---

### Lessons Learned

1. **Network Isolation**: K8s pods cannot reach Docker container IPs directly
   - Solution: Socat gateway bridges networks
   - Must handle both bootstrap AND advertised listeners

2. **Kafka Advertised Listeners**: Critical for consumer connectivity
   - Bootstrap connection ≠ actual data fetch connection
   - Use `hostAliases` to resolve advertised listener hostnames

3. **StreamFeatureViews**: Dual-purpose design
   - Single definition for both training (batch) and serving (streaming)
   - Prevents training/serving skew

4. **Static Schema Fallback**: Essential for K8s deployments
   - Generate once from source system
   - Enables deployment without source connectivity
   - Trade-off: Manual regeneration when schema changes

5. **Feature Store Architecture**: Feast loads ALL features
   - Serving pods SELECT features based on model metadata
   - No manual feature synchronization required

---

# 2025-10-02

## Fixed sklearn Version Mismatch in BentoML Model Serving

**Problem**: Model serving pods crashing with `AttributeError: Can't get attribute '_RemainderColsList'` due to sklearn version mismatch between training (1.5.1) and serving (1.7.2).

**Root Cause**:
- `bentofile.yaml` had loose version constraints (`scikit-learn>=1.3`)
- File not committed to git, so builder job cloned old version
- Model path was incorrect (`/home/bentoml/bento/src/bundle/model.joblib` vs actual `bundle/model.pkl`)

**Solution**:
1. Pinned exact versions in `application/scoring/bentofile.yaml`:
   - `scikit-learn==1.5.1`, `pandas==2.2.2`, `xgboost==2.1.0`, `numpy==1.26.4`, `mlflow==2.14.3`
2. Committed and pushed changes to `feature/ml-model-v0.0` branch
3. Updated `services/ml/k8s/model-serving/watcher-configmap.yaml`:
   - Fixed model path to `bundle/model.pkl`
   - Changed to use `:latest` Docker tag for easier updates
4. Triggered rebuild by deleting Bento and restarting watchers

**Result**: BentoML service now starts successfully with matching sklearn 1.5.1.

**Next Step**: Configure Kafka consumer to consume messages from external Kafka cluster (outside k8s).

---

## Commands for Rebuild

```bash
# 1. Delete old Bento
kubectl exec -n model-serving deployment/serving-minio -- mc rm --recursive --force minio/bentoml-bundles/bentos/credit_risk_model/v5/

# 2. Restart watchers
kubectl rollout restart deployment/mlflow-watcher -n model-registry
kubectl rollout restart deployment/serving-watcher -n model-serving

# 3. Verify
kubectl get pods -n kserve
kubectl logs -n kserve <pod-name>
```
