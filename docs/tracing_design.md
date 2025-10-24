# Distributed Tracing Design with Jaeger

## 🎯 Goal
End-to-end tracing from loan application submission to scoring result, using `SK_ID_CURR` as the trace identifier.

---

## 📊 System Architecture Map

### **Complete E2E Flow (10 Steps)**

```
┌─────────────────────────────────────────────────────────────────┐
│                       E2E Trace Flow                             │
└─────────────────────────────────────────────────────────────────┘

1️⃣  Frontend/API (Docker)
    ├─ File: application/api/main.py
    ├─ Tech: FastAPI
    ├─ Action: POST /loan_application
    └─ Span: "http_submit_application"
         ↓ Creates SK_ID_CURR, starts trace
         ↓ Inserts into PostgreSQL

2️⃣  PostgreSQL (Docker)
    ├─ Container: ops_db
    ├─ Action: INSERT into loan_applications
    └─ Span: "db_insert" (passive, measured by API)
         ↓ WAL logged
         ↓ Debezium detects change

3️⃣  Debezium CDC (Docker)
    ├─ Container: cdc-debezium
    ├─ Action: Capture change from WAL
    └─ Span: "cdc_capture"
         ↓ Publishes to Kafka with trace headers
         ↓ Topic: hc.applications.public.loan_applications

4️⃣  Kafka (Docker)
    ├─ Container: kafka_broker
    ├─ Action: Message queuing
    └─ Span: "kafka_publish" (measured by CDC)
         ↓ Message available for consumers
         ↓ Multiple consumers read in parallel

5️⃣  Flink PII Job (Docker)
    ├─ Container: flink_taskmanager
    ├─ File: application/flink/pii_job.py
    ├─ Action: Mask PII, transform data
    └─ Span: "flink_pii_transform"
         ↓ Publishes to hc.application_features
         ↓ Parallel processing (8 task slots)

6️⃣  External Bureau Service (Docker)
    ├─ Container: external-bureau-sink
    ├─ File: application/services/external_bureau_service.py
    ├─ Action: Query ClickHouse for bureau data
    └─ Span: "external_query"
         ├─ Sub-span: "clickhouse_query" (300ms typical)
         ├─ Sub-span: "data_transform"
         └─ Sub-span: "kafka_publish" → hc.application_ext

7️⃣  DWH Features Service (Docker)
    ├─ Container: dwh-features-reader
    ├─ File: application/services/dwh_features_service.py
    ├─ Action: Query PostgreSQL DWH for features
    └─ Span: "dwh_query"
         ├─ Sub-span: "postgres_query"
         └─ Sub-span: "kafka_publish" → hc.application_dwh

8️⃣  Feast Materialization (Docker)
    ├─ Container: feast-materializer-*
    ├─ File: application/feast_repo/
    ├─ Action: Read from 3 topics, write to Redis
    └─ Span: "feast_materialize"
         ├─ Reads: hc.application_features
         ├─ Reads: hc.application_ext
         ├─ Reads: hc.application_dwh
         └─ Writes: Redis feature store

9️⃣  Scoring Service (Kubernetes)
    ├─ Pod: credit-risk-v47-predictor-*
    ├─ File: application/scoring/service.py
    ├─ Action: Fetch from Feast, run model inference
    └─ Span: "scoring_inference"
         ├─ Sub-span: "feast_get_online_features" (50ms)
         ├─ Sub-span: "model_predict" (20ms)
         └─ Sub-span: "kafka_publish" → hc.scoring

🔟  Result Stored (Docker)
    ├─ Consumer reads hc.scoring
    ├─ Action: Store in ops_db
    └─ Span: "result_store"
         └─ Trace complete! ✅
```

---

## 🚨 Key Challenges

### **Challenge 1: Mixed Docker + Kubernetes Environment**

**Problem:**
- Docker services use host network/bridge network
- Kubernetes services use cluster DNS
- Need single Jaeger backend accessible by both

**Solutions:**

#### **Option A: Jaeger in Docker (Simplest)**
```yaml
# services/ops/docker-compose.tracing.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.52
    ports:
      - "16686:16686"  # Jaeger UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
      - "14268:14268"  # Jaeger collector
    environment:
      - COLLECTOR_OTLP_ENABLED=true
    networks:
      - hc-network  # Same network as other Docker services
```

**Access:**
- Docker services → `jaeger:4317` (internal DNS)
- Kubernetes services → `host.minikube.internal:4317` (host access)
- Developers → `http://localhost:16686` (Jaeger UI)

#### **Option B: Jaeger in Kubernetes (Production-ready)**
```yaml
# Deploy Jaeger operator in k8s
kubectl create namespace observability
kubectl apply -f https://github.com/jaegertracing/jaeger-operator/releases/download/v1.52.0/jaeger-operator.yaml

# Expose Jaeger to Docker services
kubectl port-forward -n observability svc/jaeger-collector 4317:4317
```

**Access:**
- Kubernetes services → `jaeger-collector.observability.svc.cluster.local:4317`
- Docker services → `localhost:4317` (via port-forward or NodePort)

**Recommendation:** Use **Option B** (Kubernetes) since you already have logging/monitoring infrastructure in k8s. This keeps all observability in one place.

**Access Pattern:**
- Kubernetes services → `jaeger-collector.observability.svc.cluster.local:4317` (cluster DNS)
- Docker services → `localhost:30317` (via NodePort)
- Developers → `http://localhost:16686` (Jaeger UI via port-forward)

---

### **Challenge 2: Capture Every Step**

**Problem:**
- 10+ services in the pipeline
- Some services are black boxes (Debezium, Kafka)
- Flink jobs need custom instrumentation

**Instrumentation Strategy:**

#### **Services We Control (Can Instrument):**

| Service | Technology | Instrumentation Method |
|---------|-----------|------------------------|
| API | FastAPI (Python) | OpenTelemetry auto-instrumentation |
| External Bureau | Python asyncio | Manual spans + async context |
| DWH Features | Python asyncio | Manual spans + async context |
| Feast Materializer | Python Kafka consumer | Manual spans + context propagation |
| Scoring Service | BentoML (Python) | Manual spans + Kafka headers |

#### **Services We Don't Control (Measure Externally):**

| Service | Technology | Measurement Strategy |
|---------|-----------|----------------------|
| PostgreSQL | Database | Measure from client side (API span) |
| Debezium | CDC connector | Estimate from Kafka publish timestamp |
| Kafka | Message broker | Measure produce/consume latency |
| Flink | Stream processing | Add custom metrics reporter |

---

### **Challenge 3: Use SK_ID_CURR as Trace ID**

**Problem:**
- OpenTelemetry generates 128-bit random trace IDs
- SK_ID_CURR is a business identifier (e.g., "123456_789")
- Need to maintain association

**Solution: Use Both IDs**

```python
# Option 1: SK_ID_CURR as trace ID (requires conversion)
import hashlib

def sk_id_to_trace_id(sk_id: str) -> str:
    """Convert SK_ID_CURR to 128-bit trace ID"""
    hash_bytes = hashlib.sha256(sk_id.encode()).digest()
    return hash_bytes[:16].hex()  # Take first 128 bits

trace_id = sk_id_to_trace_id("123456_789")
# Result: "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
```

```python
# Option 2: SK_ID_CURR as span attribute (simpler, RECOMMENDED)
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("http_submit_application") as span:
    span.set_attribute("sk_id_curr", sk_id)  # ✅ Searchable in Jaeger
    span.set_attribute("application.type", "consumer_loan")
    # ... business logic
```

**Recommendation:** Use **Option 2** - keep standard trace IDs, add `sk_id_curr` as span attribute. Jaeger UI supports searching by tags.

---

## 🔧 Technical Implementation Plan

### **Phase 1: Infrastructure Setup (Day 1)**

**Tasks:**
1. Deploy Jaeger all-in-one in Docker
2. Add OpenTelemetry SDK to all Python services
3. Configure OTLP exporters to Jaeger
4. Verify connectivity (send test spans)

**Docker Compose:**
```yaml
# services/ops/docker-compose.tracing.yml
services:
  jaeger:
    image: jaegertracing/all-in-one:1.52
    container_name: jaeger
    environment:
      - COLLECTOR_OTLP_ENABLED=true
      - SPAN_STORAGE_TYPE=badger
      - BADGER_EPHEMERAL=false
      - BADGER_DIRECTORY_VALUE=/badger/data
      - BADGER_DIRECTORY_KEY=/badger/key
    ports:
      - "16686:16686"  # UI
      - "4317:4317"    # OTLP gRPC
      - "4318:4318"    # OTLP HTTP
    volumes:
      - jaeger_data:/badger
    networks:
      - hc-network

volumes:
  jaeger_data:

networks:
  hc-network:
    external: true
```

**Python Dependencies:**
```txt
# Add to all requirements.txt files
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-exporter-otlp==1.22.0
opentelemetry-instrumentation-fastapi==0.43b0
opentelemetry-instrumentation-kafka-python==0.43b0
opentelemetry-instrumentation-psycopg2==0.43b0
opentelemetry-instrumentation-redis==0.43b0
```

---

### **Phase 2: Instrument API (Entry Point) - Day 2**

**File:** `application/api/main.py`

**Goal:** Start trace when user submits loan application

**Implementation:**
```python
# application/api/main.py
from fastapi import FastAPI
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Setup tracing
trace.set_tracer_provider(TracerProvider())
otlp_exporter = OTLPSpanExporter(
    endpoint="jaeger:4317",  # Docker DNS
    insecure=True
)
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(otlp_exporter)
)

app = FastAPI()

# Auto-instrument FastAPI (adds HTTP spans automatically)
FastAPIInstrumentor.instrument_app(app)

tracer = trace.get_tracer(__name__)

@app.post("/loan_application")
async def submit_application(application: LoanApplication):
    sk_id = f"{application.sk_id_curr}_{application.sk_id_bureau}"

    # Get current span (auto-created by FastAPI instrumentation)
    current_span = trace.get_current_span()
    current_span.set_attribute("sk_id_curr", sk_id)
    current_span.set_attribute("loan.amount", application.amt_credit)

    # Create child span for database insert
    with tracer.start_as_current_span("db_insert_application") as span:
        result = await db.insert(application)
        span.set_attribute("db.rows_affected", 1)

    return {"sk_id": sk_id, "status": "submitted"}
```

**Expected Output in Jaeger:**
```
Trace ID: abc123...
├─ http_submit_application [200ms]
│  ├─ sk_id_curr: "123456_789"
│  └─ loan.amount: 50000
   └─ db_insert_application [150ms]
      └─ db.rows_affected: 1
```

---

### **Phase 3: Kafka Context Propagation - Day 3**

**Problem:** Kafka messages don't automatically carry trace context

**Solution:** Inject trace context into Kafka headers

#### **Producer Side (API → Kafka):**
```python
from kafka import KafkaProducer
from opentelemetry.propagate import inject

producer = KafkaProducer(bootstrap_servers='kafka:9092')

# When publishing to Kafka
headers = {}
inject(headers)  # Injects trace context into headers

producer.send(
    'hc.applications',
    value=message_bytes,
    headers=list(headers.items())  # Pass trace context!
)
```

#### **Consumer Side (Kafka → Service):**
```python
from kafka import KafkaConsumer
from opentelemetry.propagate import extract

consumer = KafkaConsumer('hc.applications')

for message in consumer:
    # Extract trace context from Kafka headers
    ctx = extract(dict(message.headers))

    # Start new span with parent context
    with tracer.start_as_current_span(
        "process_application",
        context=ctx  # Links to parent trace!
    ) as span:
        span.set_attribute("sk_id_curr", message.value['sk_id_curr'])
        process(message.value)
```

**Result:** Trace continues across Kafka boundaries! 🎉

---

### **Phase 4: Instrument Docker Services - Day 4-5**

#### **External Bureau Service:**
```python
# application/services/external_bureau_service.py
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

async def query_external_data(sk_id: str, context):
    with tracer.start_as_current_span(
        "external_bureau_query",
        context=context  # From Kafka headers
    ) as span:
        span.set_attribute("sk_id_curr", sk_id)

        # Sub-span for ClickHouse query
        with tracer.start_as_current_span("clickhouse_query") as ch_span:
            start = time.time()
            result = await clickhouse.query(sql)
            ch_span.set_attribute("query.duration_ms", (time.time() - start) * 1000)
            ch_span.set_attribute("query.rows", len(result))

        # Sub-span for transformation
        with tracer.start_as_current_span("data_transform"):
            transformed = transform(result)

        return transformed
```

#### **DWH Features Service:**
```python
# application/services/dwh_features_service.py
# Similar pattern to external bureau service
```

---

### **Phase 5: Instrument Scoring Service (Kubernetes) - Day 6**

**File:** `application/scoring/service.py`

**Challenge:** Running in Kubernetes, must reach Jaeger in Docker

**Solution:**
```python
# application/scoring/service.py
import os
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

# Environment variable set in Kubernetes deployment
JAEGER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "host.minikube.internal:4317"  # Default to host
)

otlp_exporter = OTLPSpanExporter(
    endpoint=JAEGER_ENDPOINT,
    insecure=True
)

# Rest of instrumentation same as other services
```

**Kubernetes Deployment Update:**
```yaml
# services/ml/k8s/kserve/serving-watcher/watcher.py
# Add environment variable to InferenceService spec
env:
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "host.minikube.internal:4317"
  - name: OTEL_SERVICE_NAME
    value: "scoring-service"
```

---

### **Phase 6: Flink Jobs (Advanced) - Day 7**

**Challenge:** Flink is Java-based, need PyFlink or custom metrics

**Option 1: Custom Trace Headers (Simpler)**
```python
# In Flink Python job
def process_with_trace(record):
    # Extract trace context from Kafka record
    trace_id = record.get('_trace_id')
    sk_id = record.get('sk_id_curr')

    # Log timing for external monitoring
    start = time.time()
    result = process(record)
    duration = time.time() - start

    # Add timing metadata to output
    result['_trace_id'] = trace_id
    result['_flink_duration_ms'] = duration * 1000

    return result
```

**Option 2: OpenTelemetry Metrics (Better)**
- Use OpenTelemetry metrics API
- Export Flink metrics to Prometheus
- Correlate with traces in Jaeger (uses same trace IDs)

**RECOMMENDATION:** Use **Option 1** (Custom Trace Headers) for simplicity. We'll measure Flink as a black box by:
1. Recording timestamp when message enters Flink
2. Recording timestamp when message exits Flink
3. Duration = exit_time - enter_time (measured externally)

---

## 📈 Expected Results

### **Jaeger UI - Trace View:**
```
Trace: a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6
Duration: 527ms
Tags: sk_id_curr=123456_789, environment=dev

├─ http_submit_application [200ms] ← API
│  └─ db_insert [150ms]
│
├─ cdc_capture [50ms] ← Debezium (estimated)
│
├─ kafka_publish [2ms] ← Kafka
│
├─ flink_pii_transform [100ms] ← Flink
│
├─ external_bureau_query [350ms] ← Docker Service
│  ├─ clickhouse_query [300ms] ⚠️ SLOWEST!
│  └─ data_transform [50ms]
│
├─ dwh_query [120ms] ← Docker Service
│  └─ postgres_query [100ms]
│
├─ feast_materialize [80ms] ← Feast
│  ├─ kafka_consume [10ms]
│  └─ redis_write [70ms]
│
└─ scoring_inference [90ms] ← Kubernetes
   ├─ feast_get_features [50ms]
   └─ model_predict [40ms]
```

### **Insights You'll Get:**
1. ✅ **ClickHouse query is the bottleneck** (300ms / 527ms = 57% of total time)
2. ✅ **Feast materialization is healthy** (80ms is acceptable)
3. ✅ **Model inference is fast** (40ms is excellent)
4. ⚠️ **Optimization target:** Cache ClickHouse queries or add indexes

---

## 🎯 Success Metrics

**After implementing tracing, you should be able to:**

1. ✅ Search for any loan by `sk_id_curr` in Jaeger UI
2. ✅ See full E2E latency breakdown (which service is slowest)
3. ✅ Identify bottlenecks visually (longest span = bottleneck)
4. ✅ Monitor P50, P95, P99 latencies per service
5. ✅ Debug production issues (see exact step where failure occurred)
6. ✅ Validate SLA (alert if trace > 5 seconds)

---

## 📝 Next Steps for Implementation

1. **Start small:** Instrument API first (Phase 2)
2. **Validate:** Send test request, see trace in Jaeger
3. **Iterate:** Add one service at a time
4. **Monitor:** Check trace completeness (all spans present?)
5. **Optimize:** Focus on longest spans first

---

## 🤔 Open Questions for Discussion

1. **Sampling rate:** Trace 100% of requests or sample (e.g., 10%)?
   - 100% = full visibility, higher overhead
   - 10% = lower overhead, might miss rare issues
   - **DECISION: Use 10-20% sampling to avoid overhead**
   - Implementation: `TracerProvider(sampler=TraceIdRatioBased(0.1))` # 10% sampling

2. **Storage duration:** How long to keep traces?
   - Recommendation: 7 days for dev, 30 days for prod

3. **Alerting:** When to alert on trace duration?
   - Recommendation: Alert if P99 > 5 seconds

4. **Feast instrumentation depth:** Instrument internal Feast operations?
   - Recommendation: Start with black-box (measure from outside), add internal spans if needed

5. **Flink integration:** Custom metrics vs full OTEL instrumentation?
   - Recommendation: Start with custom metrics (simpler), upgrade to OTEL later

---

**Ready to start implementing? Which phase should we tackle first?**
