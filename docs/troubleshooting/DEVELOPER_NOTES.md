# 2025-10-03

## Fixed KServe Serving Pod Kafka Connectivity and Feast Integration

**Problem**: After restarting the system, both the Feast stream processor and KServe serving pods failed with Kafka connectivity errors and Feast registry access issues.

### Issues Encountered and Solutions

#### 1. Serving Pod: DNS Resolution Failure for Kafka

**Error**:
```
DNS lookup failed for host.minikube.internal:39092, exception was [Errno -3] Temporary failure in name resolution
NoBrokersAvailable
```

**Root Cause**:
- The `serving-watcher` was creating InferenceServices with incorrect `hostAliases`
- IP was set to `192.168.1.42` instead of Minikube host IP `192.168.49.1`
- Missing `host.minikube.internal` hostname mapping

**Solution**: Updated `services/ml/k8s/kserve/serving-watcher/watcher.py`

```python
# Line 168-171: Fix hostAliases configuration
"hostAliases": [{
    "ip": "192.168.49.1",  # Correct Minikube host IP
    "hostnames": ["host.minikube.internal", "broker", "kafka"]
}],
```

**Files Modified**:
- `services/ml/k8s/kserve/serving-watcher/watcher.py` (lines 168-171)

**Commands to Apply Fix**:
```bash
# Update watcher ConfigMap
kubectl create configmap serving-watcher \
  --from-file=watcher.py=services/ml/k8s/kserve/serving-watcher/watcher.py \
  -n model-serving --dry-run=client -o yaml | kubectl apply -f -

# Restart watcher
kubectl rollout restart deployment/serving-watcher -n model-serving

# Delete existing InferenceServices to force recreation
kubectl delete inferenceservice --all -n kserve
```

---

#### 2. Feast Registry: S3 Bucket Not Found

**Error**:
```
Feast lookup failed for {sk_id}: S3 bucket feast-registry for the Feast registry can't be accessed
```

**Root Cause**:
- Serving pod configured to load Feast registry from `s3://feast-registry/feature_repo/registry.db`
- The `feast-registry` bucket didn't exist in serving MinIO
- Feast registry was only available locally in the feature-registry pod

**Solution**: Upload Feast registry to MinIO S3

```bash
# 1. Copy registry from Feast pod to local
kubectl cp feature-registry/$(kubectl get pods -n feature-registry -l app=feast-stream -o jsonpath='{.items[0].metadata.name}'):data/registry.db /tmp/feast-registry.db

# 2. Copy to MinIO pod
kubectl cp /tmp/feast-registry.db model-serving/serving-minio-<pod-id>:/tmp/registry.db

# 3. Upload to S3 bucket (bucket auto-created)
kubectl exec -n model-serving serving-minio-<pod-id> -- \
  mc cp /tmp/registry.db local/feast-registry/feature_repo/registry.db

# 4. Verify upload
kubectl exec -n model-serving serving-minio-<pod-id> -- \
  mc ls local/feast-registry/feature_repo/
```

**Result**: Registry accessible at `s3://feast-registry/feature_repo/registry.db` (27 KB)

---

#### 3. Feast Stream Processor: CrashLoopBackOff

**Error**:
```
Liveness probe failed: OCI runtime exec failed: exec failed: unable to start container process: exec: "pgrep": executable file not found in $PATH
```

**Root Cause**:
- Liveness probe used `pgrep` command which doesn't exist in the Python slim container
- Kubernetes kept killing the pod even though Feast was working perfectly
- Pod would process messages successfully for ~30 seconds, then get killed

**Solution**: Updated liveness probe to use shell-based process check

**File Modified**: `services/ml/k8s/feature-store/feast-stream-deployment.yaml`

```yaml
# Before (lines 50-58):
livenessProbe:
  exec:
    command:
    - pgrep
    - -f
    - "python repository.py stream"
  initialDelaySeconds: 30
  periodSeconds: 30
  failureThreshold: 3

# After:
livenessProbe:
  exec:
    command:
    - /bin/sh
    - -c
    - "ps aux | grep '[p]ython repository.py stream'"
  initialDelaySeconds: 30
  periodSeconds: 30
  failureThreshold: 3
```

**Commands to Apply**:
```bash
# Apply updated deployment
kubectl apply -f services/ml/k8s/feature-store/feast-stream-deployment.yaml

# Restart to apply changes
kubectl rollout restart deployment/feast-stream -n feature-registry
```

---

### Verification

**1. Check Serving Pod Kafka Connection**:
```bash
kubectl logs -n kserve -l serving.kserve.io/inferenceservice=credit-risk-v11 | grep "Kafka consumer started"
# Should see: Kafka consumer started: topic=hc.applications.public.loan_applications

# Verify no DNS errors
kubectl logs -n kserve -l serving.kserve.io/inferenceservice=credit-risk-v11 | grep -i "dns\|noBrokersAvailable"
# Should be empty
```

**2. Check Feast Stream Processor**:
```bash
kubectl get pods -n feature-registry
# feast-stream pod should be Running (not CrashLoopBackOff)

kubectl logs -n feature-registry -l app=feast-stream | grep "Status:"
# Should see: Status: 3/3 consumers running
```

**3. Verify Features in Redis**:
```bash
kubectl exec -n feature-registry feast-redis-<pod> -- redis-cli KEYS "*sk_id_curr*"
# Should list customer keys like: sk_id_curr 100002hc_k8s
```

**4. Check Feast Registry Access**:
```bash
kubectl exec -n model-serving deployment/serving-minio -- \
  mc ls local/feast-registry/feature_repo/
# Should show: registry.db (27 KB)
```

---

### Key Files Modified

1. **`services/ml/k8s/kserve/serving-watcher/watcher.py`**
   - Fixed `hostAliases` IP and added `host.minikube.internal` hostname

2. **`services/ml/k8s/feature-store/feast-stream-deployment.yaml`**
   - Fixed liveness probe to use `ps aux | grep` instead of `pgrep`

3. **`services/ops/docker-compose.gateway.yml`** (from earlier session)
   - Added dynamic Kafka broker IP resolution

4. **`services/ops/restart-gateway.sh`** (from earlier session)
   - Helper script to restart gateway with correct Kafka IP

---

### Architecture Summary

```
┌──────────────────────────────────────────────────────────────┐
│           Docker Kafka (hc-network: 172.18.0.19)             │
│              Topics: hc.applications.public.*                │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────┐
│     k8s_gateway (host network) - Dynamic IP Resolution       │
│     Port 39092 → 172.18.0.19:29092 (Kafka bootstrap)         │
│     Port 29092 → 172.18.0.19:29092 (Kafka advertised)        │
└────────────────────────┬─────────────────────────────────────┘
                         │
                         ├─────────────────┬───────────────────┐
                         │                 │                   │
                         ▼                 ▼                   ▼
┌─────────────────────────────┐  ┌─────────────────┐  ┌────────────────┐
│ Feast Stream Processor      │  │ KServe Serving  │  │ Other K8s Pods │
│ (feature-registry namespace)│  │ (kserve ns)     │  │                │
│                             │  │                 │  │                │
│ hostAliases:                │  │ hostAliases:    │  │                │
│  192.168.49.1 → broker      │  │  192.168.49.1:  │  │                │
│                             │  │  - host.min...  │  │                │
│ Consumes:                   │  │  - broker       │  │                │
│  - hc.application_features  │  │  - kafka        │  │                │
│  - hc.application_ext       │  │                 │  │                │
│  - hc.application_dwh       │  │ Consumes:       │  │                │
│                             │  │  - hc.app...    │  │                │
│ Writes to ↓                 │  │  loan_apps      │  │                │
└──────────┬──────────────────┘  └────────┬────────┘  └────────────────┘
           │                              │
           ▼                              ▼
┌─────────────────────────────┐  ┌─────────────────────────────────────┐
│ Redis Online Store          │  │ MinIO S3                            │
│ (feature-registry)          │  │ (model-serving)                     │
│                             │  │                                     │
│ Features for customers:     │  │ s3://feast-registry/feature_repo/   │
│  - sk_id_curr=100002        │◄─┤   registry.db (27 KB)               │
│  - sk_id_curr=12            │  │                                     │
│  - sk_id_curr=10            │  │ Feast registry with:                │
│                             │  │  - 3 StreamFeatureViews             │
│ Queried by serving pod ─────┘  │  - 176 total features               │
│ via Feast SDK                  │  - Entity: sk_id_curr               │
└────────────────────────────────┘  └─────────────────────────────────────┘
```

---

### Lessons Learned

1. **hostAliases are Critical for Cross-Network Communication**:
   - K8s pods cannot resolve Docker container hostnames without explicit mapping
   - Must include all hostnames that appear in connection strings

2. **Liveness Probes Must Use Available Commands**:
   - Python slim images don't include `pgrep`, `ps` utilities
   - Always test probe commands in the actual container image
   - Use shell wrappers for complex checks

3. **Feast Registry Location Matters**:
   - Registry must be accessible from all services needing Feast
   - For K8s deployments, use S3/MinIO instead of local file
   - Upload registry after each `feast apply`

4. **After System Restart**:
   - Always run `restart-gateway.sh` to update Kafka IP
   - Check `hostAliases` in deployments match current IPs
   - Verify Feast registry is accessible from MinIO

---

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

## System Restart Procedures: Fixed K8s-Docker Gateway Connectivity

**Problem**: After restarting computer, Feast stream processor and other services failed with "Invalid file object: None" and Kafka connection errors.

**Root Cause**:
- Using `docker start $(docker ps -aq)` restarts containers but Docker networks don't properly reconnect
- Container IPs may change (e.g., Kafka broker moved from `172.18.0.14` → `172.18.0.19`)
- The `k8s_gateway` container had hardcoded Kafka broker IP in socat forwarding rules
- Traffic from K8s to Kafka (`host.minikube.internal:39092` → `172.18.0.14:29092`) went to wrong IP
- This caused cascading failures in Feast consumers and other Docker containers trying to reach Kafka

**Solution**: Dynamic IP resolution with helper script

### Created `services/ops/restart-gateway.sh`

Helper script that:
1. Queries Docker for current Kafka broker IP
2. Exports as environment variable
3. Recreates gateway with correct configuration

**Script**:
```bash
#!/bin/bash
# Helper script to restart k8s_gateway with current Kafka broker IP
# Run this after restarting Docker containers

set -e

cd "$(dirname "$0")"

# Get current Kafka broker IP
KAFKA_IP=$(docker inspect -f '{{range.NetworkSettings.Networks}}{{.IPAddress}}{{end}}' kafka_broker 2>/dev/null | head -1)

if [ -z "$KAFKA_IP" ]; then
    echo "ERROR: Cannot find kafka_broker container. Is it running?"
    echo "Start Kafka first with: docker start kafka_broker"
    exit 1
fi

echo "Detected Kafka broker IP: $KAFKA_IP"

# Export for docker-compose
export KAFKA_BROKER_IP=$KAFKA_IP

# Restart gateway
echo "Restarting k8s_gateway..."
docker compose -f docker-compose.gateway.yml down
docker compose -f docker-compose.gateway.yml up -d

echo "✓ Gateway restarted successfully"
docker logs k8s_gateway --tail=10
```

### Updated `services/ops/docker-compose.gateway.yml`

Changed from hardcoded IP to environment variable:

```yaml
k8s-gateway:
  image: alpine/socat:latest
  container_name: k8s_gateway
  network_mode: host  # Required for K8s-Docker bridge
  environment:
    - KAFKA_BROKER_IP=${KAFKA_BROKER_IP:-172.18.0.19}  # Dynamic IP
  command:
    - -c
    - |
      echo 'K8s Gateway Bridge starting (host network mode)...'
      echo "Using Kafka broker IP: $${KAFKA_BROKER_IP}"

      socat TCP-LISTEN:31900,reuseaddr,fork TCP:192.168.49.2:30900 &
      socat TCP-LISTEN:31901,reuseaddr,fork TCP:192.168.49.2:30901 &
      socat TCP-LISTEN:36379,reuseaddr,fork TCP:172.17.0.1:6379 &
      socat TCP-LISTEN:39092,reuseaddr,fork TCP:$${KAFKA_BROKER_IP}:29092 &
      socat TCP-LISTEN:29092,reuseaddr,fork TCP:$${KAFKA_BROKER_IP}:29092 &
      # ...
```

### Proper Restart Sequence (After Computer Restart)

```bash
# 1. Start Docker containers
docker start $(docker ps -aq)

# 2. Start Minikube
minikube start -p mlops

# 3. Restart the gateway with current Kafka IP (CRITICAL)
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ops
./restart-gateway.sh

# 4. Restart affected K8s pods (if needed)
kubectl delete pod -n feature-registry -l app=feast-stream
# Restart other affected pods as needed
```

### Why This Is Necessary

**Network Architecture**:
- Docker services run on `hc-network` (172.18.0.0/16)
- Minikube runs on separate network (192.168.49.0/24)
- `k8s_gateway` uses `network_mode: host` to bridge both networks
- Gateway forwards traffic between K8s services and Docker services

**The Problem with `docker start`**:
- Containers start but Docker network state isn't fully restored
- DHCP may assign different IPs to containers
- Gateway's socat rules still point to old IPs
- Results in "Connection refused" and "Invalid file object" errors

**Why We Use `network_mode: host`**:
- K8s pods can't directly reach Docker container IPs
- Docker containers can't directly reach K8s ClusterIPs
- Gateway on host network has access to both
- Uses socat to forward ports bidirectionally

### Verification

After running restart script, verify:

```bash
# 1. Check gateway is using correct IP
docker logs k8s_gateway | grep "Using Kafka broker IP"
# Should show: Using Kafka broker IP: 172.18.0.X (current IP)

# 2. Verify port 39092 is listening
netstat -tuln | grep 39092

# 3. Check Feast consumers are connected
kubectl logs -n feature-registry -l app=feast-stream | grep "Started.*consumer"
# Should see: ✓ Started application consumer for topic: hc.application_features
#            ✓ Started external consumer for topic: hc.application_ext
#            ✓ Started dwh consumer for topic: hc.application_dwh
```

### Troubleshooting

**If you see these errors after restart**:
- `Invalid file object: None` → Kafka connectivity broken
- `Failed to resolve 'broker:29092'` → DNS not working between containers
- `Connection refused to 172.18.0.X:29092` with old IP → Gateway using stale IP

**Solution**: Run `./restart-gateway.sh` from step 3 above.

### Files Modified

1. **`services/ops/docker-compose.gateway.yml`**
   - Changed hardcoded Kafka IP to environment variable
   - Added `KAFKA_BROKER_IP` with default fallback

2. **`services/ops/restart-gateway.sh`** (NEW)
   - Auto-detects current Kafka broker IP
   - Restarts gateway with correct configuration

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

---

# 2025-10-09

## Fixed Training-Serving Feature Mismatch with feast_metadata.yaml Contract

**Problem**: Scoring service was using hardcoded 26 features while models were trained on 43 features, causing silent prediction errors and training-serving skew.

### Root Cause Analysis

**Initial Discovery**:
- Training pipeline (Kubeflow) used 43 features selected from Feast registry
- Scoring service (`application/scoring/feature_registry.py`) had hardcoded list of 26 features
- When new features were added during training, serving pods still used old feature list
- Result: Model received incomplete feature vectors with `None` values for missing columns

**Why This Happened**:
- No contract between training and serving code
- Feature selection logic duplicated in two places
- No validation that serving uses same features as training

### Solution: feast_metadata.yaml Contract

Implemented a contract file that travels with the model from training to serving:

**1. Training Pipeline** (`services/ml/k8s/training-pipeline/pipeline.py` lines 423-437):
```python
# After feature selection, save metadata
feast_metadata = {
    "selected_features": selected_features,  # List of 43 feature names
    "num_features": len(selected_features),
    "feature_types": {"categorical": cat_cols, "numerical": num_cols},
    "training_date": datetime.now().isoformat(),
}

# Save alongside model in MLflow
with open("feast_metadata.yaml", "w") as f:
    yaml.dump(feast_metadata, f)

mlflow.log_artifact("feast_metadata.yaml")
```

**2. Bento Builder** (`services/ml/k8s/kserve/bento-builder/configmap.yaml` lines 79-93):
```python
# Download feast_metadata.yaml from MLflow artifacts
artifact_uri = model_version.source
metadata_path = f"{artifact_uri}/feast_metadata.yaml"

try:
    client.download_artifacts(run_id, "feast_metadata.yaml", local_dir)
    shutil.copy(f"{local_dir}/feast_metadata.yaml", f"{bento_path}/src/bundle/")
    logger.info("✓ feast_metadata.yaml packaged with Bento")
except Exception as e:
    logger.warning(f"⚠ No feast_metadata.yaml found: {e}")
```

**3. Scoring Service** (`application/scoring/model_registry.py` lines 149-166):
```python
def load_model(*, source: str, path: Optional[str], mlflow_uri: Optional[str]):
    """Load model AND its feature metadata."""

    # Load feast_metadata.yaml from bundle directory
    model_dir = os.path.dirname(os.path.abspath(path))
    metadata_path = os.path.join(model_dir, "feast_metadata.yaml")

    if os.path.exists(metadata_path):
        with open(metadata_path, "r") as f:
            feast_metadata = yaml.safe_load(f)
        logger.info(f"✓ Loaded feast metadata: {feast_metadata.get('num_features', 0)} features")
        return model, name, version, feast_metadata
    else:
        logger.warning("⚠ No feast_metadata.yaml - using feature_registry.py fallback")
        return model, name, version, None
```

**4. Feature Selection in Service** (`application/scoring/service.py` lines 287-304):
```python
def _get_expected_columns() -> List[str]:
    """Get features from model's metadata, not hardcoded list."""
    global _EXPECTED_COLUMNS
    if _EXPECTED_COLUMNS is None:
        # Priority 1: Use model's actual training features
        if MODEL_FEAST_METADATA and MODEL_FEAST_METADATA.get("selected_features"):
            _EXPECTED_COLUMNS = MODEL_FEAST_METADATA["selected_features"]
            logger.info(f"Using {len(_EXPECTED_COLUMNS)} features from model's feast_metadata.yaml")
        else:
            # Priority 2: Fallback to hardcoded registry
            _EXPECTED_COLUMNS = get_model_expected_columns()
            logger.warning(f"Using {len(_EXPECTED_COLUMNS)} features from hardcoded feature_registry.py")
    return _EXPECTED_COLUMNS
```

**Result**: Scoring service now automatically uses the exact same 43 features the model was trained on.

---

### Issue 2: Kafka Consumer Not Starting in Serving Pods

**Error**: Logs showed "Initializing scoring service" but no "Kafka consumer started" message.

**Root Cause**:
- Checked pod environment: `SCORING_ENABLE_KAFKA=false`
- InferenceService was created BEFORE watcher ConfigMap was updated with Kafka settings
- Watcher's `create_or_update_inferenceservice()` had `"SCORING_ENABLE_KAFKA": "false"`

**Solution**:
1. Updated `services/ml/k8s/model-serving/watcher-configmap.yaml` line 197:
   ```yaml
   {"name": "SCORING_ENABLE_KAFKA", "value": "true"},
   ```

2. Applied updated ConfigMap and restarted watcher:
   ```bash
   kubectl apply -f services/ml/k8s/model-serving/watcher-configmap.yaml
   kubectl rollout restart -n model-serving deployment/serving-watcher
   ```

3. Deleted existing InferenceService to force recreation:
   ```bash
   kubectl delete inferenceservice -n kserve credit-risk-v13
   ```

4. Watcher automatically recreated v13 with Kafka enabled.

**Verification**:
```bash
# Check environment
kubectl exec -n kserve credit-risk-v13-predictor-xxx -- env | grep SCORING_ENABLE_KAFKA
# Output: SCORING_ENABLE_KAFKA=true ✅

# Check logs
kubectl logs -n kserve credit-risk-v13-predictor-xxx | grep "Kafka consumer started"
# Output: Kafka consumer started: topic=hc.applications.public.loan_applications ✅
```

---

### Issue 3: Kafka DNS Resolution Failure

**Error**: After Kafka consumer started, pods failed with:
```
DNS lookup failed for broker:29092
NoBrokersAvailable
```

**Root Cause Analysis**:
- Consumer connected to bootstrap server: `host.minikube.internal:39092` ✅
- Kafka metadata response said: "Real broker is at `broker:29092`"
- KServe pods couldn't resolve hostname `broker` → connection failed ❌

**Why This Happened**:
1. Kafka advertised listener is `broker:29092` (configured in Docker Compose)
2. K8s pods only know about `host.minikube.internal` (via hostAliases)
3. After bootstrap connection, Kafka tells consumer "now connect to `broker:29092` for data"
4. Pod tries DNS lookup for `broker` → fails

**Solution**: Created Kubernetes Service with Endpoints

Created `services/ml/k8s/kserve/kafka-broker-service.yaml`:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: broker
  namespace: kserve
spec:
  ports:
  - port: 29092
    targetPort: 29092
    protocol: TCP
---
apiVersion: v1
kind: Endpoints
metadata:
  name: broker
  namespace: kserve
subsets:
- addresses:
  - ip: 192.168.49.1  # Minikube host IP (adjust if needed)
  ports:
  - port: 39092  # Socat gateway port
```

**How It Works**:
1. Pod tries to connect to `broker:29092`
2. K8s DNS resolves `broker` to Service ClusterIP
3. Service forwards to Endpoint: `192.168.49.1:39092`
4. Socat gateway forwards to Docker Kafka: `172.18.0.x:29092`
5. Connection succeeds! ✅

**Apply Fix**:
```bash
kubectl apply -f services/ml/k8s/kserve/kafka-broker-service.yaml
```

**Verification**:
```bash
kubectl logs -n kserve credit-risk-v13-predictor-xxx | grep -i "dns\|NoBrokersAvailable"
# Output: (empty - no errors) ✅

kubectl logs -n kserve credit-risk-v13-predictor-xxx | grep "stream_inference"
# Output:
# {'sk_id_curr': '33', 'probability': 0.10496515, 'decision': 'approve'} ✅
```

---

### Final Working Architecture

```
Streamlit Form Submission
    ↓
PostgreSQL (loan_applications table)
    ↓
Debezium CDC
    ↓
Kafka: hc.applications.public.loan_applications
    ↓
Docker → host:39092 (socat gateway)
    ↓
KServe Pod (v13 predictor)
  - SCORING_ENABLE_KAFKA=true ✅
  - Connects to host.minikube.internal:39092 (bootstrap)
  - Resolves broker:29092 via Service/Endpoints ✅
  - Kafka Consumer Thread Running ✅
    ↓
Extract sk_id_curr from CDC message
    ↓
Feast.get_online_features(sk_id_curr=X)
  - Uses 43 features from feast_metadata.yaml ✅
  - Fetches from Redis online store
    ↓
Model.predict_proba(X) with 43 features ✅
    ↓
Publish prediction to logs (event=stream_inference)
```

---

### Key Files Modified

1. **`services/ml/k8s/training-pipeline/pipeline.py`**
   - Added feast_metadata.yaml generation after feature selection
   - Logs metadata to MLflow artifacts

2. **`services/ml/k8s/kserve/bento-builder/configmap.yaml`**
   - Downloads feast_metadata.yaml from MLflow
   - Packages it into Bento bundle at `src/bundle/feast_metadata.yaml`

3. **`application/scoring/model_registry.py`**
   - Loads feast_metadata.yaml from bundle directory
   - Returns metadata alongside model

4. **`application/scoring/service.py`**
   - Uses model's features from metadata instead of hardcoded list
   - Lazy-loads feature list on first prediction

5. **`services/ml/k8s/model-serving/watcher-configmap.yaml`**
   - Fixed `SCORING_ENABLE_KAFKA` to `"true"`
   - Configured Kafka bootstrap servers, topic, consumer group

6. **`services/ml/k8s/kserve/kafka-broker-service.yaml`** (NEW)
   - Service to resolve `broker:29092` DNS name
   - Endpoints pointing to socat gateway at host:39092

---

### Verification Commands

**Check v13 is deployed with latest code**:
```bash
kubectl get inferenceservice -n kserve
# Should show: credit-risk-v13

kubectl get pods -n kserve -l serving.kserve.io/inferenceservice=credit-risk-v13
# Should show: Running
```

**Verify feast_metadata.yaml was loaded**:
```bash
kubectl logs -n kserve <v13-predictor-pod> | grep "feast_metadata"
# Expected:
# ✓ Loaded feast metadata from /home/bentoml/bento/src/bundle/feast_metadata.yaml: 43 features
# Using 43 features from model's feast_metadata.yaml
```

**Verify Kafka consumer is running**:
```bash
kubectl logs -n kserve <v13-predictor-pod> | grep "Kafka consumer"
# Expected:
# Kafka consumer started: topic=hc.applications.public.loan_applications, group=credit-risk-scoring
```

**Test end-to-end flow**:
```bash
# Submit loan application via Streamlit
# Check scoring pod logs for prediction
kubectl logs -n kserve <v13-predictor-pod> --tail=20 | grep "stream_inference"

# Expected output:
# {'sk_id_curr': 'X', 'probability': 0.XXX, 'decision': 'approve/reject', ...}
```

**Verify no DNS errors**:
```bash
kubectl logs -n kserve <v13-predictor-pod> | grep -i "dns\|NoBrokersAvailable"
# Should be empty (no errors)
```

---

### Lessons Learned

1. **Training-Serving Contracts Are Critical**:
   - Never hardcode feature lists in serving code
   - Package metadata (feature names, types, counts) with the model
   - Validate at startup that serving has all required features

2. **Kafka Advertised Listeners in K8s**:
   - Bootstrap connection ≠ data connection
   - Kafka metadata response contains advertised listener hostname
   - K8s needs Service/Endpoints to resolve external hostnames
   - Can't rely on hostAliases alone when crossing network boundaries

3. **ConfigMap Updates Require Pod Recreation**:
   - Updating a ConfigMap doesn't automatically update running pods
   - InferenceServices created before ConfigMap update have stale config
   - Must delete and recreate pods to pick up new environment variables

4. **Feature Metadata Should Travel With Model**:
   - Training pipeline → MLflow artifacts → Bento bundle → Serving pod
   - Single source of truth prevents drift
   - Makes debugging easier (pod logs show exactly which features are used)

5. **Test The Whole Flow, Not Just Parts**:
   - Kafka consumer thread starting ≠ consumer working
   - Must verify actual message consumption and prediction
   - Check both control plane (pod status) and data plane (actual predictions)

---

### Next Steps

With the serving pipeline now fully working, the next priorities are:

1. **External Data Integration**:
   - Create Kafka topics: `bureau_raw`, `bureau_balance_raw`, `application_ext_raw`
   - Move transformation logic from `application/services/external_bureau_service.py` to Flink
   - Implement Flink jobs for: raw → clean transformation
   - Update Feast to consume from clean topics

2. **Documentation Updates**:
   - Update README.md with kafka-broker-service.yaml setup
   - Document the feast_metadata.yaml contract pattern
   - Add troubleshooting section for Kafka DNS issues

3. **Monitoring**:
   - Add metrics for feature loading success/failure
   - Track prediction latency with 43 vs 26 features
   - Monitor Kafka consumer lag

---
