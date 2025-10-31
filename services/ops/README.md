# Ops Scripts

This directory contains operational scripts for managing the Home Credit ML platform infrastructure.

## Scripts Overview

### `fresh-start.sh`
**Purpose**: Create a clean environment for load testing by clearing all application data.

**When to use**:
- Before starting load tests (ensures clean baseline)
- After architecture changes that invalidate old data
- When Kafka consumer groups have stale message backlogs

**Usage**:
```bash
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ops
./fresh-start.sh
```

**What it does**:
1. **Truncates PostgreSQL** - Removes all loan applications (operations.public.loan_applications)
2. **Flushes Redis** - Clears all materialized features
3. **Deletes InferenceServices** - Removes all KServe scoring deployments completely
4. **Purges hc.feature_ready topic** - Deletes old feature_ready messages (sets retention to 1s then restores)
5. **Resets Kafka consumer groups** - Moves all offsets to LATEST:
   - `external-bureau-sink`
   - `dwh-features-reader`
   - `credit-risk-scoring` (including `hc.feature_ready` topic)
   - `feast-materializer-external`
   - `feast-materializer-application`
   - `feast-materializer-dwh`
6. **Waits for auto-recreation** - serving-watcher automatically recreates InferenceServices from MLflow (45-75 seconds)
7. **Verifies system** - Shows consumer group lag and pod status

**Result**:
- PostgreSQL: 0 rows
- Redis: 0 keys
- Kafka hc.feature_ready: Old messages purged
- Kafka consumer groups: All offsets at LATEST (LAG = 0)
- InferenceServices: Freshly recreated with clean state
- All services: Restarted and healthy

---

### `clear-kafka-backlog.sh`
**Purpose**: Reset Kafka consumer group offsets to LATEST without touching PostgreSQL/Redis.

**When to use**:
- When you only need to clear Kafka message backlogs
- Called automatically by `fresh-start.sh`

**Usage**:
```bash
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ops
./clear-kafka-backlog.sh
```

---

### `restart-gateway.sh`
**Purpose**: Restart k8s_gateway with the current Kafka broker IP address.

**When to use**:
- After restarting Docker containers
- When you see "Invalid file object: None" errors in Feast logs
- After Kafka broker IP changes

**Usage**:
```bash
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ops
./restart-gateway.sh
```

**What it does**:
1. Detects current Kafka broker IP from Docker
2. Exports `KAFKA_BROKER_IP` environment variable
3. Restarts k8s_gateway container with updated IP
4. Shows gateway logs for verification

---

### `restart-k8s-after-minikube.sh`
**Purpose**: Comprehensive restart of all critical K8s deployments after `minikube start`.

**When to use**:
- Immediately after running `minikube start -p mlops`
- When multiple pods are in CrashLoopBackOff after cluster restart
- As part of your system startup routine

**Usage**:
```bash
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ops
./restart-k8s-after-minikube.sh
```

**What it does**:
1. Waits for Kubernetes API server to be ready
2. Waits for CoreDNS to be healthy
3. Restarts k8s_gateway with current Kafka IP
4. Restarts critical deployments:
   - cert-manager components
   - KServe controller
   - Kubeflow controllers (workflow, cache, metadata)
   - MLflow watcher
   - Ray operator
   - Feast stream processor
5. Fixes storage provisioner if needed
6. Waits for all deployments to become ready
7. Provides summary of cluster health

---

## Complete System Restart Procedure

After restarting your computer or minikube, follow this sequence:

```bash
# 1. Start Docker containers
docker start $(docker ps -aq)

# 2. Start Minikube cluster
minikube start -p mlops

# 3. Wait a moment for cluster initialization (30-60 seconds)
sleep 30

# 4. Run the comprehensive restart script
cd /home/nhatquang/home-credit-credit-risk-model-stability/services/ops
./restart-k8s-after-minikube.sh

# 5. Verify everything is running
kubectl get pods --all-namespaces | grep -E "CrashLoopBackOff|Error"
```

**Expected result**: No pods should be in CrashLoopBackOff (except possibly `feast-apply` which is a job).

---

## Troubleshooting

### Kafka connectivity errors in Feast
**Symptom**: `Invalid file object: None` or `NoBrokersAvailable`

**Solution**:
```bash
./restart-gateway.sh
kubectl rollout restart deployment/feast-stream -n feature-registry
```

### Pods stuck in CrashLoopBackOff
**Symptom**: Multiple pods showing CrashLoopBackOff after minikube start

**Solution**:
```bash
./restart-k8s-after-minikube.sh
```

### API server timeout errors
**Symptom**: Logs showing `dial tcp 10.96.0.1:443: i/o timeout`

**Cause**: Pods started before API server networking was ready

**Solution**: Restart the affected deployment:
```bash
kubectl rollout restart deployment <deployment-name> -n <namespace>
```

---

## Environment Variables

### `KAFKA_BROKER_IP`
Used by `docker-compose.gateway.yml` to configure socat port forwarding.

**How it's set**:
- Automatically detected by `restart-gateway.sh`
- Defaults to `172.18.0.19` if not set

**Why it's needed**:
Docker assigns dynamic IPs to containers. After restart, the Kafka broker may get a different IP. The gateway must forward to the current IP for K8s pods to reach Kafka.

---

## Related Files

- `docker-compose.gateway.yml` - K8s gateway configuration
- `docker-compose.orchestration.yml` - Airflow orchestration
- `../ml/k8s/feature-store/` - Feast configuration
- `../../Developer_Notes.md` - Detailed troubleshooting history

---

## Notes

- The `restart-k8s-after-minikube.sh` script includes the functionality of `restart-gateway.sh`
- Run `restart-k8s-after-minikube.sh` for comprehensive post-restart recovery
- Run `restart-gateway.sh` for quick Kafka connectivity fixes
- Both scripts are safe to run multiple times
