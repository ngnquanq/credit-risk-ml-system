# Feast + Redis Kubernetes Deployment Status

**Date**: 2025-09-30
**Status**: ✅ Feast and Redis successfully deployed and running

## What's Deployed

### 1. Redis (Online Feature Store)
- **Deployment**: `feast-redis` - 1 replica running
- **Service**: `feast-redis:6379` (ClusterIP)
- **Purpose**: Stores materialized feature values for real-time serving
- **Resource**: 256Mi-512Mi memory, 100m-500m CPU

### 2. Feast Registry (PVC)
- **PVC**: `feast-registry` (100Mi)
- **Mount**: `/work/data/` in both feast pods
- **Contents**: `registry.db` with feature metadata
- **Shared by**: feast-apply job and feast-stream deployment

### 3. Feast Apply (Job)
- **Status**: Completed successfully
- **Purpose**: Registered feature definitions to registry
- **Registered**:
  - 1 entity: `customer` (join key: `sk_id_curr`)
  - 3 StreamFeatureViews: `application_features`, `external_features`, `dwh_features`
  - 1 FeatureService: `realtime_scoring_v1`
- **Project**: `hc_k8s`

### 4. Feast Stream (Deployment)
- **Deployment**: `feast-stream` - 1 replica running
- **Purpose**: Consumes from 3 Kafka topics and materializes to Redis
- **Kafka Topics**:
  1. `hc.application_features` - Flink-processed application data (13 fields, 1 day TTL)
  2. `hc.application_ext` - External bureau features (7 fields, 7 days TTL)
  3. `hc.application_dwh` - ClickHouse data warehouse features (156 fields, 7 days TTL)
- **Kafka Broker**: `172.18.0.13:29092` (container IP on hc-network)

## Architecture Details

### Network Configuration
- **mlops container** connected to `hc-network` bridge network
- Kubernetes pods can access Docker Compose services via container IPs:
  - Kafka: `172.18.0.13:29092`
  - ClickHouse: `172.18.0.36:8123`

### Data Flow
```
Kafka Topics → feast-stream pod → Redis (feature values)
                              ↓
                           PVC (registry metadata)
                              ↑
         BentoML service → Feast client → Redis (query features)
```

### Registry Contents (registry.db)
Stores feature metadata:
- Entity definitions (customer with sk_id_curr)
- StreamFeatureView schemas (field names, types, TTLs)
- Data source configurations (Kafka topics)
- Online store config (Redis connection)
- Feature service definitions

**Does NOT store**: Actual feature values (those are in Redis)

## Configuration Files

All manifests located in: `/services/ml/k8s/feature-store-kustomize/`

1. **redis-deployment.yaml** - Redis deployment + service
2. **feast-configmap.yaml** - Environment variables (Kafka brokers, topics, project name)
3. **feast-store-config.yaml** - ConfigMap with `feature_store.yaml` (Redis connection for K8s)
4. **feast-registry-pvc.yaml** - PVC for shared registry
5. **feast-apply-job.yaml** - One-time job to register features
6. **feast-stream-deployment.yaml** - Long-running Kafka consumer
7. **kustomization.yaml** - Main Kustomize config

### Key Configuration Values
- **Project name**: `hc_k8s` (underscores only, no hyphens)
- **Docker image**: `feast-repo:v2` (built from `application/feast/`)
- **Namespace**: `feature-registry`

## Deployment Commands

```bash
# Deploy everything
kubectl apply -k /home/nhatquang/home-credit-credit-risk-model-stability/services/ml/k8s/feature-store/ --context=mlops

# Check status
kubectl get pods -n feature-registry --context=mlops
kubectl get pvc -n feature-registry --context=mlops

# View logs
kubectl logs -n feature-registry --context=mlops -l app=feast-stream -f
kubectl logs -n feature-registry --context=mlops job/feast-apply

# Query registry
kubectl exec -n feature-registry --context=mlops deployment/feast-stream -- python3 -c "
from feast import FeatureStore
fs = FeatureStore(repo_path='/work')
print('Stream FVs:', len(list(fs.list_stream_feature_views())))
"
```

## Next Steps: BentoML Serving Service

**What's needed:**
1. BentoML deployment manifest
2. Mount `feast-store-config` ConfigMap for Feast client
3. Access to `feast-redis:6379` service
4. ML model artifact (from MLflow)
5. Service/Ingress for external access

**BentoML will:**
- Receive prediction requests with `sk_id_curr`
- Query Feast: `fs.get_online_features(entity_rows=[{"sk_id_curr": "123"}], features=[...])`
- Feast fetches from Redis
- Run model inference
- Return predictions

## Issues Resolved

1. **HostPath volume mount failure** - Fixed by embedding Feast repo in Docker image instead of mounting
2. **Registry conflicts** - Fixed by using separate project name (`hc_k8s`) and fresh registry.db
3. **Feast project name validation** - Changed from `hc-k8s` to `hc_k8s` (no hyphens allowed)
4. **Image caching** - Fixed by tagging as `v2` and loading fresh image to Minikube
5. **Registry not shared** - Fixed by creating PVC mounted at `/work/data/` in both pods

## Verification

**All systems operational:**
- ✅ Redis running and accessible
- ✅ Registry shared via PVC
- ✅ 3 StreamFeatureViews registered
- ✅ feast-stream consuming from 3 Kafka topics
- ✅ Features being materialized to Redis

**Ready for**: BentoML serving service deployment