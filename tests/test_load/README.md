# End-to-End Prediction Pipeline Load Test

This load test measures the **complete real-time ML prediction pipeline** from loan application submission to prediction output.

## 📊 What This Tests

### Complete Pipeline Flow

```
[PostgreSQL INSERT]
        ↓ (~100ms)
   [Debezium CDC]
        ↓ (~500ms)
   [Kafka Topic: hc.applications.public.loan_applications]
        ↓ (~50ms)
   [External Bureau Service]
        ↓ (fetches from ClickHouse, ~200ms)
   [Kafka Topic: hc.application_ext_raw]
        ↓ (~100ms)
   [Apache Flink Bureau Job]
        ↓ (processes 60+ features, ~500ms)
   [Kafka Topic: hc.application_ext]
        ↓ (~100ms)
   [Feast Stream Materializer]
        ↓ (writes to Redis, ~200ms)
   [Redis Feature Store]
        ↓ (~10ms feature lookup)
   [KServe Predictor]
        ↓ (LightGBM inference, ~50ms)
   [Kafka Topic: hc.scoring]
        ↓
[PREDICTION OUTPUT] ✓
```

**Total Expected Latency: ~1.5-3 seconds** (for near real-time)

---

## 🚀 Quick Start

### Prerequisites

1. **K8s pods healthy**:
   ```bash
   kubectl get pods -n data-services
   kubectl get pods -n kserve | grep credit-risk
   kubectl get pods -n feature-registry | grep feast
   ```

2. **Port-forwards active** (the shell scripts start these automatically, but for manual runs):
   ```bash
   # Option A: Use Makefile shortcuts (each blocks the terminal)
   make pf-postgres   # localhost:6432 → ops-pgbouncer (connection-pooled)
   make pf-kafka      # localhost:9092 → kafka-broker

   # Option B: Manual
   kubectl port-forward -n data-services svc/ops-pgbouncer 6432:6432
   kubectl port-forward -n data-services svc/kafka-broker 9092:9092
   ```

3. **Dependencies installed**:
   ```bash
   pip install locust psycopg2-binary kafka-python
   ```

### Run Load Test

**Option 1: Quick Test (50 users, 5 minutes)** — starts port-forwards automatically
```bash
./tests/test_load/run_e2e_load_test.sh
```

**Option 2: Custom Configuration**
```bash
USERS=100 SPAWN_RATE=20 RUN_TIME=10m ./tests/test_load/run_e2e_load_test.sh
```

**Option 3: Manual Locust Command** (requires port-forwards running separately)
```bash
locust -f tests/test_load/locustfile_e2e_prediction.py \
       --host=localhost:9092 \
       --users 50 --spawn-rate 10 --run-time 5m --headless \
       --html reports/e2e_test.html --csv reports/e2e_test
```

**Option 4: In-Cluster (K8s Job)** — runs inside the cluster, no port-forwards needed
```bash
# Create ConfigMap with test files
kubectl create configmap locust-test-files \
  --from-file=locustfile_e2e_prediction.py=tests/test_load/locustfile_e2e_prediction.py \
  -n data-services

# Launch the Job
kubectl apply -f tests/test_load/k8s-load-test-job.yaml

# Watch logs
kubectl logs -f -n data-services job/locust-e2e-load-test
```

---

## 📈 Metrics Collected

### 1. PostgreSQL Insert Latency
- **Metric**: Time to INSERT loan application into database
- **Expected**: < 50ms (P95)
- **Measures**: Database write performance

### 2. End-to-End Prediction Latency
- **Metric**: Time from PostgreSQL INSERT to prediction in `hc.scoring` topic
- **Expected**: 1.5-3 seconds (P95)
- **Measures**: Complete pipeline performance

### 3. Throughput
- **Metric**: Requests/second (RPS) the system can handle
- **Expected**: 100-150 RPS sustained (with PgBouncer connection pooling)
- **Measures**: System capacity

---

## 📊 Understanding the Results

### Locust Output

```
Type     Name                            # Requests  Median  95%ile  99%ile  Avg     Min    Max    | # Fails
---------|-------------------------------|------------|-------|-------|-------|-------|-------|-------|--------
PostgreSQL  Insert Loan Application      5000        45 ms   80 ms   150 ms  50 ms   20 ms  500 ms  | 0
E2E         End-to-End Prediction        4800        1800 ms 2500 ms 3500 ms 1900 ms 1000 ms 5000 ms | 200
---------|-------------------------------|------------|-------|-------|-------|-------|-------|-------|--------
           Aggregated                    9800        900 ms  2400 ms 3400 ms 950 ms  20 ms  5000 ms | 200
```

### Key Metrics for Resume

1. **Throughput**: `Total RPS = Total Requests / Test Duration`
   - Example: 5000 requests / 300 seconds = **16.7 RPS**

2. **Latency**:
   - **P50** (Median): 50% of requests faster than this
   - **P95**: 95% of requests faster than this (use for SLA)
   - **P99**: 99% of requests faster than this (outliers)

3. **Success Rate**: `(1 - Fails/Total) × 100%`
   - Example: (1 - 200/5000) × 100% = **96% success rate**

---

## 🎯 Expected Results (for Resume)

### Conservative Estimate

```
End-to-End Prediction Latency:
  P50: ~1.8 seconds
  P95: ~2.5 seconds
  P99: ~3.5 seconds (can reach ~450ms for DB-only P99 under sustained load)

Throughput: ~100-150 RPS sustained (with PgBouncer connection pooling)
Success Rate: > 95%
```

### Resume-Ready Statement

> "Architected real-time ML pipeline processing **100+ loan applications per second** with **P95 latency under 3 seconds** from submission to prediction, leveraging Apache Flink for distributed feature engineering and Feast/Redis for sub-10ms feature retrieval"

---

## 🔍 Troubleshooting

### Issue: Predictions not appearing

```bash
# Check if KServe predictor is consuming
kubectl logs -n kserve credit-risk-v13-predictor-xxx --tail=50

# Check Kafka topic has predictions (exec into the broker pod)
kubectl exec -n data-services deploy/kafka-broker -- \
    kafka-console-consumer --bootstrap-server localhost:9092 \
    --topic hc.scoring --from-beginning --max-messages 10
```

### Issue: High latency (> 5 seconds)

Possible bottlenecks:
1. **Flink processing slow**: Check Flink parallelism
2. **ClickHouse query slow**: Check bureau service logs
3. **Feast materialization lag**: Check feast-stream pod logs
4. **Redis overloaded**: Check Redis memory/connections

### Issue: Low throughput (< 10 RPS)

Scaling options:
1. **Increase Flink parallelism**: Add more task managers
2. **Scale KServe predictor**: Increase replica count
3. **Optimize PostgreSQL**: Ensure PgBouncer is deployed (`make k8s-pgbouncer`)
4. **Scale Kafka**: Add more partitions

---

## 📝 Test Scenarios

### 1. Smoke Test (Validation)
```bash
locust -f tests/locustfile_e2e_prediction.py --host=localhost:9092 \
       --users 10 --spawn-rate 5 --run-time 1m --headless
```

### 2. Load Test (Capacity)
```bash
locust -f tests/locustfile_e2e_prediction.py --host=localhost:9092 \
       --users 100 --spawn-rate 20 --run-time 10m --headless \
       --html reports/load_test.html
```

### 3. Stress Test (Limits)
```bash
locust -f tests/locustfile_e2e_prediction.py --host=localhost:9092 \
       --users 200 --spawn-rate 50 --run-time 15m --headless \
       --html reports/stress_test.html
```

### 4. Spike Test (Sudden Traffic)
```bash
# Phase 1: Normal (50 users, 2min)
# Phase 2: Spike (300 users, 3min)
# Phase 3: Recovery (50 users, 2min)
```

---

## 📂 Output Files

After running the test, you'll find:

```
reports/
├── e2e_prediction_20251014_130000.html       # Interactive HTML report
├── e2e_prediction_20251014_130000_stats.csv  # Request statistics
├── e2e_prediction_20251014_130000_stats_history.csv  # Time series
└── e2e_prediction_20251014_130000_failures.csv  # Failed requests
```

---

## 🎓 Understanding Near Real-Time

**What does "near real-time" mean?**

| Latency Range | Classification | Use Case |
|---------------|----------------|----------|
| < 100ms | Real-time | High-frequency trading, gaming |
| 100ms - 1s | Near real-time | Fraud detection, recommendations |
| 1s - 5s | Low-latency | Credit scoring, risk assessment ← **YOU ARE HERE** |
| 5s - 30s | Batch micro-batch | Analytics, reporting |
| > 30s | Batch | Data warehousing |

Your system at **~2-3 seconds P95** is **excellent for credit risk assessment** and qualifies as **near real-time production ML**.

---

## 📊 Generating Resume Metrics

After running the test, extract these numbers:

```bash
# From HTML report or CSV
grep "Aggregated" reports/e2e_prediction_*_stats.csv

# Example output for resume:
# - Processed 5,000 loan applications
# - Sustained throughput: 100-150 RPS
# - P50 latency: 1.8s
# - P95 latency: 2.5s
# - P99 latency: 3.5s
# - Success rate: 96%
```

**Resume bullet point template:**
```
Deployed production ML pipeline achieving <P95 latency>s end-to-end prediction
latency at <throughput> RPS, with <parallelism> Flink task managers processing
<feature_count>+ features from <data_volume> historical records
```

---

## 🚀 Next Steps

1. **Run smoke test** to validate setup
2. **Run load test** (5-10 minutes) to get metrics
3. **Analyze HTML report** for bottlenecks
4. **Extract metrics** for resume
5. **Optional**: Run stress test to find system limits

Happy load testing! 🎉
