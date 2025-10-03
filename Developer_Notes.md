# 2025-10-03

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
