# Knative Eventing Migration Status

## ✅ Completed Steps

### 1. Knative Stack Installation
- **Knative Serving v1.13.1** - Installed with Kourier networking layer (replaced failed net-istio)
- **Knative Eventing v1.13.7** - Installed successfully
- **Knative Kafka v1.13.6** - KafkaSource and KafkaSink controllers deployed

```bash
kubectl get deployment -n knative-serving
# activator, autoscaler, controller, net-kourier-controller, webhook - ALL READY

kubectl get deployment -n knative-eventing
# eventing-controller, kafka-controller, kafka-sink-receiver, kafka-webhook-eventing - ALL READY
```

### 2. KServe Integration
- Enabled Knative addressable resolver in KServe controller:
```bash
kubectl set env deployment/kserve-controller-manager -n kserve ENABLE_KNATIVE_ADDRESSABLE_RESOLVER=true
```

### 3. BentoML Code Refactoring
- ✅ Commented out Kafka consumer code in `application/scoring/service.py` (NOT deleted per user request)
- ✅ Updated `application/scoring/config.py` - `enable_kafka=False`
- ✅ Removed kafka-python from `application/scoring/bentofile.yaml`
- ✅ Added error handling for missing features in `/v1/score-by-id` endpoint

### 4. Infrastructure Resources
- ✅ Created serverless InferenceService template: `isvc-template-serverless.yaml`
- ✅ Updated serving watcher with KafkaSource management logic
- ✅ Created KafkaSource manifest: `kafka-source.yaml`
- ✅ Created RBAC resources: `kafka-rbac.yaml`
- ✅ Created Knative Serving configuration
- ✅ Updated Makefile with installation targets

### 5. Kafka Topics
- ✅ Created `hc.scoring` topic (3 partitions)
- ✅ Created `hc.scoring.dlq` topic (1 partition)
- ✅ Existing `hc.feature_ready` topic ready for consumption

---

## ⚠️ Current Blocker: KafkaSink Connectivity

### Problem
The Knative kafka-controller validates Kafka topics during KafkaSink reconciliation, but it's trying to connect to `127.0.0.1:29092` (default) instead of `host.minikube.internal:39092` (where Docker Kafka is accessible via socat).

### Root Cause
- Kafka runs in Docker, not Kubernetes
- Socat bridge provides access at `host.minikube.internal:39092`
- KafkaSink controller has no global bootstrap server configuration
- Controller falls back to hardcoded default `127.0.0.1:29092` for topic validation

### Error Logs
```
topics [hc.scoring] not present or invalid: failed to describe topics:
dial tcp 127.0.0.1:29092: connect: connection refused
```

### Status of KafkaSinks
```bash
kubectl get kafkasink -n kserve
# NAME                  READY   REASON
# scoring-output-sink   False   Topic is not present or invalid
# scoring-dlq-sink      False   Topic is not present or invalid
```

---

## 🎯 Next Steps - Phased Approach

### Phase 1: Input Pipeline (READY TO TEST)
Deploy KafkaSource → InferenceService flow WITHOUT output publishing:

```bash
# 1. Deploy KafkaSource (DLQ commented out)
kubectl apply -f services/ml/k8s/kserve/kafka-source.yaml

# 2. Wait for existing InferenceService or deploy new one
kubectl get isvc -n kserve

# 3. Test by publishing to hc.feature_ready topic
docker exec kafka_broker kafka-console-producer \
  --bootstrap-server localhost:9092 \
  --topic hc.feature_ready \
  --property "parse.key=true" \
  --property "key.separator=:" \
  <<< '100001:{"sk_id_curr":"100001","source":"test","ts":"2024-01-10T12:00:00Z"}'

# 4. Monitor KafkaSource dispatcher logs
kubectl logs -n knative-eventing statefulset/kafka-source-dispatcher -f

# 5. Monitor InferenceService logs
kubectl logs -n kserve -l serving.kserve.io/inferenceservice=credit-risk-latest -f
```

### Phase 2: Output Publishing (BLOCKED - Needs Resolution)

**Option A: Fix KafkaSink connectivity**
- Configure kafka-controller with default bootstrap servers
- OR create Kafka bootstrap server ConfigMap/Secret
- OR use Kafka auth configuration in KafkaSink specs

**Option B: Hybrid approach**
- Keep KafkaSource for input (event-driven)
- Re-enable Kafka producer in BentoML for output (direct publishing)
- This loses full event-driven benefits but is pragmatic

**Option C: Use Knative Broker + Trigger pattern**
- Replace KafkaSink with Knative Broker
- Use Triggers to route responses back to Kafka
- More complex but avoids KafkaSink validation issue

---

## 📊 Architecture Status

### Current Working Flow
```
Kafka (hc.feature_ready)
  ↓ [via socat at host.minikube.internal:39092]
KafkaSource (knative-eventing)
  ↓ [HTTP POST /v1/score-by-id]
InferenceService (kserve namespace)
  ↓ [returns JSON response]
??? (OUTPUT PUBLISHING NOT YET CONNECTED)
```

### Target Flow (When Complete)
```
Kafka (hc.feature_ready)
  ↓
KafkaSource
  ↓
InferenceService
  ↓ [HTTP response with CloudEvents]
KafkaSink
  ↓
Kafka (hc.scoring)
```

---

## 🔧 Technical Details

### Knative Networking
- **Ingress Controller**: Kourier (not Istio/Gateway API due to compatibility)
- **Service Mesh**: None (using Kourier's built-in routing)
- **DNS**: Knative uses cluster-local DNS for service discovery

### Autoscaling Configuration
- **minScale**: 1 (always warm for consistent SLA)
- **maxScale**: 10
- **Target concurrency**: 100 requests
- **Metric**: Knative Pod Autoscaler (KPA) with concurrency-based scaling
- **Scale-down delay**: 30s

### Resource Limits (per pod)
```yaml
requests:
  cpu: 1500m
  memory: 768Mi
limits:
  cpu: 2000m
  memory: 1152Mi
```

---

## 📝 Files Modified/Created

### Modified Files
1. `application/scoring/service.py` - Commented out Kafka consumer (lines 558-691)
2. `application/scoring/config.py` - Set `enable_kafka=False`
3. `application/scoring/bentofile.yaml` - Removed kafka-python
4. `services/ml/k8s/kserve/serving-watcher/watcher.py` - Added KafkaSource management
5. `Makefile` - Added Knative installation targets

### New Files
1. `services/ml/k8s/knative/serving-config.yaml`
2. `services/ml/k8s/knative/kafka-rbac.yaml`
3. `services/ml/k8s/kserve/serving-watcher/isvc-template-serverless.yaml`
4. `services/ml/k8s/kserve/kafka-source.yaml`
5. `services/ml/k8s/kserve/kafka-sink.yaml`
6. `services/ml/k8s/kserve/kafka-dlq-sink.yaml`

---

## 🚨 Important Notes

1. **Kafka consumer code is COMMENTED OUT, not deleted** - Easy rollback if needed
2. **Socat bridge is critical** - K8s pods reach Docker Kafka via `host.minikube.internal:39092`
3. **Topics must exist before KafkaSink** - Controller validates topic existence
4. **No model retraining needed** - Only serving layer changes

---

## 📚 References

- [CARS24 Async ML Inference](https://autonauts.cars24.com/blog/knative-eventing-and-kserve)
- [Knative Eventing Documentation](https://knative.dev/docs/eventing/)
- [KServe Serverless](https://kserve.github.io/website/latest/modelserving/v1beta1/serving_runtime/)
- [Kafka Source Documentation](https://knative.dev/docs/eventing/sources/kafka-source/)
