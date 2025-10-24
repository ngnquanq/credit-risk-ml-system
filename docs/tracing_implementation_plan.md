# Jaeger Tracing Implementation Plan

## 📋 Implementation Summary

**Decisions Made:**
1. ✅ **Jaeger in Kubernetes** (consistent with existing observability stack)
2. ✅ **Flink as black box** (measure externally for simplicity)
3. ✅ **10% sampling rate** (avoid overhead)
4. ✅ **Full pipeline instrumentation** (all services)

---

## 🎯 Implementation Phases

### **Phase 0: Prerequisites (30 minutes)**

**Goal:** Set up Jaeger backend in Kubernetes

**Steps:**

1. **Create observability namespace:**
```bash
kubectl create namespace observability
```

2. **Deploy Jaeger All-in-One:**
```yaml
# services/ml/k8s/observability/jaeger.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: jaeger
  namespace: observability
spec:
  replicas: 1
  selector:
    matchLabels:
      app: jaeger
  template:
    metadata:
      labels:
        app: jaeger
    spec:
      containers:
      - name: jaeger
        image: jaegertracing/all-in-one:1.52
        env:
        - name: COLLECTOR_OTLP_ENABLED
          value: "true"
        - name: SPAN_STORAGE_TYPE
          value: "badger"
        ports:
        - containerPort: 16686  # UI
          name: ui
        - containerPort: 4317   # OTLP gRPC
          name: otlp-grpc
        - containerPort: 4318   # OTLP HTTP
          name: otlp-http
        - containerPort: 14268  # Jaeger collector
          name: collector
        volumeMounts:
        - name: jaeger-storage
          mountPath: /badger
      volumes:
      - name: jaeger-storage
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: jaeger-collector
  namespace: observability
spec:
  type: NodePort
  selector:
    app: jaeger
  ports:
  - port: 4317
    targetPort: 4317
    nodePort: 30317  # Docker services will use localhost:30317
    name: otlp-grpc
  - port: 4318
    targetPort: 4318
    nodePort: 30318
    name: otlp-http
---
apiVersion: v1
kind: Service
metadata:
  name: jaeger-ui
  namespace: observability
spec:
  type: NodePort
  selector:
    app: jaeger
  ports:
  - port: 16686
    targetPort: 16686
    nodePort: 30686  # Access UI at localhost:30686
    name: ui
```

3. **Deploy Jaeger:**
```bash
kubectl apply -f services/ml/k8s/observability/jaeger.yaml

# Verify deployment
kubectl get pods -n observability
kubectl get svc -n observability
```

4. **Access Jaeger UI:**
```bash
# Option 1: Via NodePort
open http://localhost:30686

# Option 2: Via port-forward
kubectl port-forward -n observability svc/jaeger-ui 16686:16686
open http://localhost:16686
```

5. **Test connectivity:**
```bash
# From host (Docker services will use this)
curl http://localhost:30317

# From k8s (scoring service will use this)
kubectl run test --image=curlimages/curl -it --rm -- \
  curl http://jaeger-collector.observability.svc.cluster.local:4317
```

---

### **Phase 1: Instrument API (Entry Point) - 1 hour**

**Files to modify:**
- `application/api/main.py`
- `application/requirements-api.txt`

**1. Add dependencies:**
```txt
# application/requirements-api.txt
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-exporter-otlp-proto-grpc==1.22.0
opentelemetry-instrumentation-fastapi==0.43b0
opentelemetry-instrumentation-psycopg2==0.43b0
```

**2. Create tracing utility:**
```python
# application/api/tracing.py
import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

def setup_tracing(service_name: str, sampling_rate: float = 0.1):
    """
    Setup OpenTelemetry tracing

    Args:
        service_name: Name of the service (appears in Jaeger)
        sampling_rate: 0.1 = 10% of traces (avoid overhead)
    """
    # Get Jaeger endpoint from environment (different for Docker vs k8s)
    jaeger_endpoint = os.getenv(
        "OTEL_EXPORTER_OTLP_ENDPOINT",
        "localhost:30317"  # Default: Docker services → k8s NodePort
    )

    # Create tracer provider with sampling
    provider = TracerProvider(
        sampler=TraceIdRatioBased(sampling_rate)  # 10% sampling
    )

    # Create OTLP exporter
    otlp_exporter = OTLPSpanExporter(
        endpoint=jaeger_endpoint,
        insecure=True  # No TLS for internal communication
    )

    # Add batch processor (efficient, batches spans before sending)
    provider.add_span_processor(BatchSpanProcessor(otlp_exporter))

    # Set as global tracer provider
    trace.set_tracer_provider(provider)

    print(f"✅ Tracing initialized: {service_name} → {jaeger_endpoint}")

    return trace.get_tracer(service_name)
```

**3. Instrument FastAPI:**
```python
# application/api/main.py
from fastapi import FastAPI, HTTPException
from opentelemetry import trace
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from .tracing import setup_tracing

# Initialize tracing BEFORE creating FastAPI app
tracer = setup_tracing("api-service", sampling_rate=0.1)

app = FastAPI(title="Home Credit API")

# Auto-instrument FastAPI (adds HTTP spans automatically)
FastAPIInstrumentor.instrument_app(app)

@app.post("/loan_application")
async def submit_application(application: LoanApplication):
    """
    Submit a new loan application

    This endpoint is the ENTRY POINT for distributed tracing.
    A trace starts here and propagates through the entire pipeline.
    """
    # Get current span (auto-created by FastAPI instrumentation)
    current_span = trace.get_current_span()

    # Add business context as span attributes (searchable in Jaeger)
    sk_id = f"{application.sk_id_curr}_{application.sk_id_bureau}"
    current_span.set_attribute("sk_id_curr", sk_id)
    current_span.set_attribute("loan.amount", application.amt_credit)
    current_span.set_attribute("loan.type", "consumer_loan")
    current_span.set_attribute("environment", "dev")

    # Create child span for database operation
    with tracer.start_as_current_span("db_insert_application") as db_span:
        try:
            # Insert into PostgreSQL
            start_time = time.time()
            result = await db.insert(application)
            duration_ms = (time.time() - start_time) * 1000

            # Add metrics to span
            db_span.set_attribute("db.system", "postgresql")
            db_span.set_attribute("db.operation", "INSERT")
            db_span.set_attribute("db.table", "loan_applications")
            db_span.set_attribute("db.rows_affected", 1)
            db_span.set_attribute("db.duration_ms", duration_ms)

        except Exception as e:
            # Record error in span
            db_span.record_exception(e)
            db_span.set_status(Status(StatusCode.ERROR, str(e)))
            raise HTTPException(status_code=500, detail=str(e))

    # At this point, Debezium CDC will capture the change
    # and propagate the trace context to Kafka

    return {
        "sk_id": sk_id,
        "status": "submitted",
        "trace_id": format(current_span.get_span_context().trace_id, "032x")
    }

@app.get("/health")
async def health():
    """Health check (not traced to avoid noise)"""
    return {"status": "healthy"}
```

**4. Update docker-compose:**
```yaml
# services/core/docker-compose.api.yml
services:
  api:
    build: ../../application
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=host.docker.internal:30317
      - OTEL_SERVICE_NAME=api-service
    ports:
      - "8000:8000"
```

**5. Test:**
```bash
# Start API
docker-compose -f services/core/docker-compose.api.yml up

# Send test request
curl -X POST http://localhost:8000/loan_application \
  -H "Content-Type: application/json" \
  -d '{"sk_id_curr": 123456, "sk_id_bureau": 789, "amt_credit": 50000}'

# Check Jaeger UI
open http://localhost:30686
# Search for: sk_id_curr:123456_789
```

**Expected result:** See trace with 2 spans:
1. `http_submit_application` (parent)
2. `db_insert_application` (child)

---

### **Phase 2: Kafka Context Propagation - 1 hour**

**Challenge:** Traces must flow across Kafka topics

**Files to modify:**
- All Kafka producers and consumers

**1. Create Kafka tracing utility:**
```python
# application/core/kafka_tracing.py
from opentelemetry import trace
from opentelemetry.propagate import inject, extract
from opentelemetry.trace import Status, StatusCode
from kafka import KafkaProducer, KafkaConsumer
import json

class TracingKafkaProducer:
    """
    Kafka producer with automatic trace context propagation

    Usage:
        producer = TracingKafkaProducer('kafka:9092')
        producer.send_traced('topic', {'data': 123}, sk_id='123456_789')
    """

    def __init__(self, bootstrap_servers, **kwargs):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            **kwargs
        )
        self.tracer = trace.get_tracer(__name__)

    def send_traced(self, topic: str, value: dict, sk_id: str = None):
        """Send message with trace context in headers"""

        with self.tracer.start_as_current_span(f"kafka_publish_{topic}") as span:
            # Add context
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", topic)
            span.set_attribute("messaging.operation", "publish")
            if sk_id:
                span.set_attribute("sk_id_curr", sk_id)

            # Inject trace context into headers
            headers = {}
            inject(headers)  # Adds 'traceparent' and 'tracestate'

            # Convert headers to Kafka format [(key, value), ...]
            kafka_headers = [(k, str(v).encode('utf-8')) for k, v in headers.items()]

            try:
                # Send with trace headers
                future = self.producer.send(
                    topic,
                    value=value,
                    headers=kafka_headers
                )

                # Wait for confirmation (optional, adds latency)
                # future.get(timeout=10)

                span.set_attribute("messaging.success", True)

            except Exception as e:
                span.record_exception(e)
                span.set_status(Status(StatusCode.ERROR, str(e)))
                raise


class TracingKafkaConsumer:
    """
    Kafka consumer with automatic trace context extraction

    Usage:
        consumer = TracingKafkaConsumer('topic', 'kafka:9092', 'my-group')
        for message, context in consumer.consume_traced():
            with tracer.start_as_current_span("process", context=context):
                process(message)
    """

    def __init__(self, topic, bootstrap_servers, group_id, **kwargs):
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            **kwargs
        )
        self.tracer = trace.get_tracer(__name__)

    def consume_traced(self):
        """Consume messages with trace context extraction"""
        for message in self.consumer:
            # Extract trace context from Kafka headers
            headers_dict = {
                k.decode('utf-8'): v.decode('utf-8')
                for k, v in message.headers or []
            }

            # Extract creates a Context object that links to parent trace
            parent_context = extract(headers_dict)

            yield message.value, parent_context
```

**2. Update API to use tracing producer:**
```python
# application/api/main.py (continued)
from core.kafka_tracing import TracingKafkaProducer

# Initialize at startup
producer = TracingKafkaProducer('kafka:9092')

@app.post("/loan_application")
async def submit_application(application: LoanApplication):
    # ... existing code ...

    # After DB insert, publish to Kafka (optional, if needed)
    # Usually Debezium CDC does this automatically
    # But if you want manual control:

    # producer.send_traced(
    #     'hc.applications.manual',
    #     value=application.dict(),
    #     sk_id=sk_id
    # )

    return {"sk_id": sk_id}
```

**3. Verify CDC propagates headers:**

CDC (Debezium) should automatically copy trace headers from the database to Kafka. If not, we'll measure CDC as a black box (timing difference between DB insert and Kafka message).

---

### **Phase 3: External Bureau Service - 1.5 hours**

**Files to modify:**
- `application/services/external_bureau_service.py`
- `application/services/bureau_client.py`

**1. Add dependencies:**
```txt
# application/services/requirements-service.txt
opentelemetry-api==1.22.0
opentelemetry-sdk==1.22.0
opentelemetry-exporter-otlp-proto-grpc==1.22.0
opentelemetry-instrumentation-kafka-python==0.43b0
```

**2. Instrument service:**
```python
# application/services/external_bureau_service.py
import asyncio
import time
from opentelemetry import trace
from core.kafka_tracing import TracingKafkaConsumer, TracingKafkaProducer
from .tracing import setup_tracing

# Setup tracing
tracer = setup_tracing("external-bureau-service", sampling_rate=0.1)

# Initialize Kafka
consumer = TracingKafkaConsumer(
    'hc.applications.public.loan_applications',
    'kafka:9092',
    'external-bureau-sink'
)

producer = TracingKafkaProducer('kafka:9092')

async def query_clickhouse(sk_id: str):
    """Query ClickHouse for external bureau data"""

    with tracer.start_as_current_span("clickhouse_query") as span:
        span.set_attribute("db.system", "clickhouse")
        span.set_attribute("sk_id_curr", sk_id)

        start = time.time()

        # Your existing query logic
        query = f"""
        SELECT
            sk_id_curr,
            -- ... your fields
        FROM external_bureau
        WHERE sk_id_curr = {sk_id}
        """

        try:
            result = await clickhouse_client.execute(query)
            duration_ms = (time.time() - start) * 1000

            span.set_attribute("db.query_duration_ms", duration_ms)
            span.set_attribute("db.rows_returned", len(result))
            span.set_attribute("db.query_length", len(query))

            return result

        except Exception as e:
            span.record_exception(e)
            span.set_status(Status(StatusCode.ERROR, str(e)))
            raise


async def transform_bureau_data(raw_data):
    """Transform bureau data"""

    with tracer.start_as_current_span("transform_bureau_data") as span:
        span.set_attribute("data.input_rows", len(raw_data))

        # Your transformation logic
        transformed = your_transformation_function(raw_data)

        span.set_attribute("data.output_rows", len(transformed))

        return transformed


async def process_message(message: dict, parent_context):
    """
    Process one loan application message

    Args:
        message: Loan application data
        parent_context: Trace context from Kafka headers (links to API trace)
    """

    # Start span with parent context (continues the trace from API!)
    with tracer.start_as_current_span(
        "external_bureau_process",
        context=parent_context  # 🔥 This links to the original trace!
    ) as span:

        sk_id = message.get('sk_id_curr')
        span.set_attribute("sk_id_curr", sk_id)

        # Query ClickHouse (child span created inside)
        bureau_data = await query_clickhouse(sk_id)

        # Transform data (child span created inside)
        transformed = await transform_bureau_data(bureau_data)

        # Publish to output topic with trace context
        producer.send_traced(
            'hc.application_ext',
            value=transformed,
            sk_id=sk_id
        )


async def main():
    """Main consumer loop"""
    print("🚀 External Bureau Service started")

    # Consume with trace context
    for message, parent_context in consumer.consume_traced():
        try:
            await process_message(message, parent_context)
        except Exception as e:
            print(f"❌ Error processing {message.get('sk_id_curr')}: {e}")


if __name__ == "__main__":
    asyncio.run(main())
```

**3. Update docker-compose:**
```yaml
# services/data/docker-compose.query-services.yml
services:
  external-bureau-sink:
    build: ../../application/services
    environment:
      - OTEL_EXPORTER_OTLP_ENDPOINT=host.docker.internal:30317
      - OTEL_SERVICE_NAME=external-bureau-service
    command: python external_bureau_service.py
```

**4. Test:**
```bash
# Start service
docker-compose -f services/data/docker-compose.query-services.yml up

# Send test message (via API)
curl -X POST http://localhost:8000/loan_application ...

# Check Jaeger UI
# You should now see:
# 1. API span
# 2. External bureau span (child of API!)
# 3. ClickHouse query span (child of external bureau)
```

---

### **Phase 4: DWH Features Service - 1 hour**

**Same pattern as External Bureau Service**

Files: `application/services/dwh_features_service.py`

(Apply same instrumentation pattern as above)

---

### **Phase 5: Feast Materialization - 1 hour**

**Challenge:** Feast materializes from 3 topics into Redis

**Files to modify:**
- `application/feast_repo/` (custom materialization script if you have one)

**Pattern:**
```python
# Consume from all 3 topics with trace context
consumer_app = TracingKafkaConsumer(...)
consumer_ext = TracingKafkaConsumer(...)
consumer_dwh = TracingKafkaConsumer(...)

# Create span for materialization
with tracer.start_as_current_span("feast_materialize", context=parent_context):
    # Write to Redis
    redis_client.set(...)
```

---

### **Phase 6: Scoring Service (Kubernetes) - 1 hour**

**Files to modify:**
- `application/scoring/service.py`
- `application/scoring/config.py`
- `services/ml/k8s/kserve/serving-watcher/watcher.py`

**1. Add tracing to scoring service:**
```python
# application/scoring/service.py
import os
from opentelemetry import trace
from .tracing import setup_tracing

# Get Jaeger endpoint (different in k8s)
# This will be set by watcher.py
JAEGER_ENDPOINT = os.getenv(
    "OTEL_EXPORTER_OTLP_ENDPOINT",
    "jaeger-collector.observability.svc.cluster.local:4317"
)

tracer = setup_tracing("scoring-service", sampling_rate=0.1)

@bentoml.service
class CreditRiskScoring:

    def _run_kafka_consumer(self):
        """Consume from Kafka and run inference"""

        consumer = TracingKafkaConsumer(
            'hc.applications.public.loan_applications',
            'kafka:9092',
            'credit-risk-scoring'
        )

        for message, parent_context in consumer.consume_traced():
            with tracer.start_as_current_span(
                "scoring_inference",
                context=parent_context
            ) as span:
                sk_id = message.get('sk_id_curr')
                span.set_attribute("sk_id_curr", sk_id)

                # Fetch features from Feast
                with tracer.start_as_current_span("feast_get_features") as feast_span:
                    features = self.feast_client.get_online_features(...)
                    feast_span.set_attribute("feast.features_count", len(features))

                # Run model inference
                with tracer.start_as_current_span("model_predict") as model_span:
                    prediction = self.model.predict(features)
                    model_span.set_attribute("model.version", MODEL_VERSION)
                    model_span.set_attribute("prediction.probability", prediction)

                # Publish result
                producer.send_traced('hc.scoring', result, sk_id=sk_id)
```

**2. Update watcher to inject Jaeger endpoint:**
```python
# services/ml/k8s/kserve/serving-watcher/watcher.py

# In create_inference_service():
env_vars = [
    # Existing env vars...
    {
        "name": "OTEL_EXPORTER_OTLP_ENDPOINT",
        "value": "jaeger-collector.observability.svc.cluster.local:4317"
    },
    {
        "name": "OTEL_SERVICE_NAME",
        "value": f"scoring-service-{version}"
    }
]
```

---

### **Phase 7: Flink (Black Box) - 30 minutes**

**Approach:** Measure externally (before/after timestamps)

**Option 1: Add timing in Kafka messages:**
```python
# Before Flink (API or upstream service)
message['_flink_entry_ts'] = time.time()

# After Flink (downstream service)
if '_flink_entry_ts' in message:
    flink_duration = time.time() - message['_flink_entry_ts']
    current_span.set_attribute("flink.duration_ms", flink_duration * 1000)
```

**Option 2: Create synthetic span:**
```python
# In downstream service (e.g., External Bureau)
with tracer.start_as_current_span("flink_pii_transform_estimated") as span:
    # This is a synthetic span representing Flink processing
    # We estimate duration based on Kafka timestamps
    span.set_attribute("estimated", True)
    span.set_attribute("duration_ms", estimated_duration)
```

---

## 📈 Validation Checklist

After implementing all phases, verify:

- [ ] Jaeger UI accessible at `http://localhost:30686`
- [ ] Send test loan application via API
- [ ] Search Jaeger for `sk_id_curr:123456_789`
- [ ] See complete E2E trace with all services:
  - [ ] API (http_submit_application)
  - [ ] External Bureau (external_bureau_process)
  - [ ] DWH Features (dwh_query)
  - [ ] Feast (feast_materialize)
  - [ ] Scoring (scoring_inference)
- [ ] Identify bottleneck visually (longest span)
- [ ] P99 latency < 5 seconds

---

## 🚀 Quick Start Commands

```bash
# 1. Deploy Jaeger
kubectl apply -f services/ml/k8s/observability/jaeger.yaml
kubectl get pods -n observability -w

# 2. Rebuild Docker images with tracing
docker-compose -f services/core/docker-compose.api.yml build
docker-compose -f services/data/docker-compose.query-services.yml build

# 3. Restart services
docker-compose -f services/core/docker-compose.api.yml up -d
docker-compose -f services/data/docker-compose.query-services.yml up -d

# 4. Rebuild scoring service
cd application/scoring
bentoml build
docker push ngnquanq/credit-risk-scoring:latest

# 5. Restart watcher (will redeploy with new env vars)
kubectl rollout restart deployment -n model-serving serving-watcher

# 6. Open Jaeger UI
open http://localhost:30686

# 7. Send test request
curl -X POST http://localhost:8000/loan_application \
  -H "Content-Type: application/json" \
  -d '{"sk_id_curr": 123456, "amt_credit": 50000}'

# 8. Search in Jaeger for: sk_id_curr:123456_789
```

---

## 🎯 Expected Outcome

**Before Tracing:**
- "My prediction takes 3 minutes... why??" 🤔
- Guessing which service is slow
- No visibility into E2E flow

**After Tracing:**
- See exact breakdown:
  - API: 200ms
  - External Bureau: 350ms (ClickHouse: 300ms) ← **BOTTLENECK!**
  - DWH: 120ms
  - Feast: 80ms
  - Scoring: 90ms
- Know exactly what to optimize
- Search any loan by SK_ID_CURR
- Monitor SLA violations (P99 > 5s)

---

**Ready to start with Phase 0 (Jaeger deployment)?**
