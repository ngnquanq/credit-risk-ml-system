# K8s Components Audit - README vs Reality

## Components Mentioned in README

### ✅ **Implemented & Working**

1. **Kubeflow Pipelines** (README lines 349-357)
   - README: Install from GitHub manifests
   - Reality: ✅ Correctly documented

2. **Training Data Storage (MinIO)** (README lines 359-393)
   - README: Helm install in `training-data` namespace
   - Reality: ✅ Exists at `services/ml/k8s/training-data-storage`
   - README: MetalLB config for external access
   - Reality: ✅ ConfigMap exists at `services/ml/k8s/training-data-storage/metallb/configmap.yaml`

3. **Model Registry (MLflow)** (README lines 395-409)
   - README: Helm install in `model-registry` namespace
   - Reality: ✅ Exists at `services/ml/k8s/model-registry`
   - README: PostgreSQL + MinIO backends
   - Reality: ✅ Charts include both postgresql and minio subcharts

4. **MLflow Watcher** (README lines 411-445)
   - README: Polls MLflow, triggers bento-build Job
   - Reality: ✅ Exists at `services/ml/k8s/mlflow-watcher/`
   - Files: `rbac.yaml`, `poller-configmap.yaml`, `builder-configmap.yaml`, `deployment.yaml`

5. **KServe** (README lines 447-462)
   - README: Install cert-manager, gateway-api, KServe CRD + controller
   - Reality: ✅ Exists at `services/ml/k8s/kserve/`
   - README: Helm charts for kserve-crd and kserve-main
   - Reality: ✅ Both subdirs exist

6. **Model Serving (BentoML + Watcher)** (README lines 465-497)
   - README: Create `model-serving` namespace
   - README: DockerHub secrets for image pull
   - README: Deploy MinIO for bundles, Docker registry, serving watcher
   - Reality: ✅ All exist at `services/ml/k8s/model-serving/`
   - Files: `bundle-storage/`, `registry-deployment.yaml`, `watcher-*.yaml`

7. **Cert Manager** (README lines 508-513)
   - README: Install in `cert-manager` namespace
   - Reality: ✅ Exists at `services/ops/k8s/cert-manager/`

8. **Ray Cluster** (README lines 515-527)
   - README: KubeRay operator + RayCluster
   - Reality: ✅ Exists at `services/ml/k8s/kuberay-operator/`
   - Files: `raycluster.yaml`

9. **Training Pipeline** (README lines 530-533)
   - README: Compile pipeline to YAML
   - Reality: ✅ Script exists at `services/ml/k8s/training-pipeline/compile_pipeline.py`

---

### ⚠️ **Mentioned but Incomplete/Outdated**

10. **Nginx Gateway** (README lines 338-345)
    - README says:
      ```bash
      kubectl apply -f ./services/ml/k8s/gateway/configmap-stream.yaml
      helm install k8s-gateway . -f values.internal.yaml -n nginx
      ```
    - Reality: ⚠️ `services/ml/k8s/gateway/` exists BUT:
      - `configmap-stream.yaml` exists ✅
      - `values.internal.yaml` exists ✅
      - **NO `Chart.yaml`** - the `helm install` command would **FAIL**
    - **Status**: Partially implemented, README needs update

11. **Socat** (README line 347)
    - README: "Additionally, we will use socat for connec" ⚠️ **INCOMPLETE SENTENCE**
    - Reality: No socat manifests found in `services/ml/k8s/`
    - Socat exists in Docker Compose (`services/ops/docker-compose.gateway.yml`)
    - **Status**: Missing from K8s deployment, only exists in Docker Compose

---

### ❌ **Missing from README but Exists**

12. **Kafka Broker Service** (NEW - created during troubleshooting)
    - Reality: ✅ Created to fix Kafka DNS resolution
    - File: `services/ml/k8s/kserve/kafka-broker-service.yaml`
    - Purpose: Maps `broker:29092` DNS name to `host.minikube.internal:39092` (socat gateway)
    - **Status**: **Exists but NOT documented in README**
    - **Recommendation**: Add to KServe setup section

13. **Bento Builder ConfigMap** (Referenced but path unclear)
    - README: References "bento-builder-script" ConfigMap (line 619)
    - Reality: ✅ Exists at `services/ml/k8s/kserve/bento-builder/configmap.yaml`
    - **Status**: Exists but deployment steps not in README
    - **Recommendation**: Add explicit `kubectl apply` command

---

## Redundant or Potentially Unnecessary Components

### 1. **Multiple MinIO Instances**
- **training-data** namespace: MinIO for training data snapshots
- **model-registry** namespace: MinIO for MLflow model artifacts
- **model-serving** namespace: MinIO for Bento bundles
- **Assessment**: ✅ **NOT redundant** - each serves a distinct purpose with different lifecycles

### 2. **Docker Registry Strategy Confusion**
- README line 476 creates `dockerhub-creds` secret (implies using DockerHub)
- README line 490 deploys in-cluster Docker registry (`registry-deployment.yaml`)
- **Problem**: Unclear which registry is actually used
- **Current Reality**: Watcher pushes to DockerHub (`docker.io/ngnquanq/credit-risk-scoring`)
- **Assessment**: In-cluster registry deployment appears **unused**
- **Recommendation**:
  - Either remove in-cluster registry deployment, OR
  - Document when to use which (e.g., "use in-cluster for airgapped environments")

### 3. **MySQL Chart in model-registry**
- Chart includes both `charts/mysql/` and `charts/postgresql/`
- MLflow only uses one backend database
- Current setup uses PostgreSQL (based on `values.internal.yaml`)
- **Assessment**: MySQL chart is **unused**
- **Recommendation**: Remove `charts/mysql/` to reduce confusion and maintenance burden

---

## Scripts Executed But NOT in README

### From Recent Implementation Work:
1. ❌ `kubectl apply -f services/ml/k8s/kserve/kafka-broker-service.yaml`
2. ❌ `kubectl apply -f services/ml/k8s/kserve/bento-builder/configmap.yaml`
3. ❌ `kubectl apply -f services/ml/k8s/model-serving/watcher-configmap.yaml` (updated with Kafka settings)
4. ❌ `kubectl rollout restart -n model-serving deployment/serving-watcher` (to pick up config changes)

---

## Scripts in README That Will FAIL

1. **Line 343**: `helm install k8s-gateway . -f values.internal.yaml -n nginx`
   - **Problem**: No `Chart.yaml` in `services/ml/k8s/gateway/`
   - **Error**: `Error: validation: chart.metadata is required`
   - **Fix Options**:
     - Create proper Helm chart with `Chart.yaml`, OR
     - Change README to use `kubectl apply -f services/ml/k8s/gateway/configmap-stream.yaml`

---

## Incomplete Documentation

### 1. Socat Setup (Line 347)
- **Current text**: "Additionally, we will use socat for connec"
- **Problem**: Sentence is incomplete
- **Missing info**:
  - Socat runs in Docker Compose, not K8s
  - Forwards `host:39092` → `kafka_broker:29092`
  - K8s pods access it via `host.minikube.internal:39092`
  - Requires `kafka-broker-service.yaml` in KServe namespace for DNS

### 2. Troubleshooting Section (Lines 575-621)
- Documents the **problem** (feature mismatch, `feast_metadata.yaml`)
- Documents the **verification** steps
- ✅ This section is accurate and helpful
- ⚠️ **Missing**: How to handle Kafka connectivity issues between K8s and Docker Compose

---

## Recommendations

### High Priority Fixes:

1. **Fix Gateway Setup** (line 338-345)
   ```bash
   # Either add Chart.yaml or change to:
   kubectl create ns nginx
   kubectl apply -f ./services/ml/k8s/gateway/configmap-stream.yaml -n nginx
   ```

2. **Complete Socat Section** (line 347)
   ```markdown
   Additionally, we use socat (running in Docker Compose) to forward Kafka traffic:
   - Socat listens on `host:39092` and forwards to `kafka_broker:29092`
   - K8s pods access Kafka via `host.minikube.internal:39092`
   - For DNS resolution in KServe namespace, apply the broker service:
     ```bash
     kubectl apply -f services/ml/k8s/kserve/kafka-broker-service.yaml
     ```
   ```

3. **Add Bento Builder ConfigMap** (after line 462)
   ```markdown
   # Deploy BentoML builder ConfigMap (used by mlflow-watcher)
   kubectl apply -f services/ml/k8s/kserve/bento-builder/configmap.yaml
   ```

4. **Document Kafka Broker Service** (after KServe install, line 462)
   ```markdown
   # Configure Kafka DNS resolution for scoring pods
   kubectl apply -f services/ml/k8s/kserve/kafka-broker-service.yaml
   ```

### Medium Priority Cleanups:

5. **Clarify Registry Strategy** (lines 471-478)
   - Document that DockerHub is used (current implementation)
   - Remove or clearly mark `registry-deployment.yaml` as optional

6. **Remove MySQL Chart**
   - Delete `services/ml/k8s/model-registry/charts/mysql/`
   - Only keep PostgreSQL chart

### Low Priority Improvements:

7. **Add Troubleshooting Entry** for Kafka connectivity
8. **Create checklist** of all required `kubectl apply` commands in order
9. **Add verification steps** after each major component installation

---

## Summary Statistics

- ✅ **Working as documented**: 9 components
- ⚠️ **Partially working/outdated**: 2 components (Nginx gateway, Socat)
- ❌ **Undocumented but required**: 2 files (kafka-broker-service.yaml, bento-builder configmap)
- 🗑️ **Potentially unnecessary**: 2 components (in-cluster registry, MySQL chart)
- 📝 **README issues**: 1 incomplete sentence, 1 failing command

**Overall Assessment**: The K8s setup is **mostly complete and functional**, but the README has several gaps that would cause confusion for someone following it from scratch. The recent fixes for Kafka connectivity and feast_metadata.yaml are not yet reflected in the documentation.
