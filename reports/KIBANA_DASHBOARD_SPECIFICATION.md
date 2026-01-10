# Kibana Dashboard Specification - Credit Risk Prediction Pipeline

**Purpose**: Real-time monitoring of end-to-end ML prediction pipeline performance
**Data Sources**: Elasticsearch (via Filebeat from Docker containers & K8s pods)
**Target Users**: ML Engineers, DevOps, Product Managers

---

## Dashboard Overview

This dashboard visualizes the complete journey of a loan application through the real-time prediction pipeline:

```
User Request → API Gateway → PostgreSQL → Debezium CDC → Kafka
  → Flink Feature Engineering → Feast Feature Store → KServe Inference
  → Prediction Result
```

---

## Section 1: Pipeline Success Rate & Throughput (Top KPIs)

### 1.1 Overall Success Rate (Single Value)
**Metric**: Percentage of applications that successfully complete end-to-end prediction
**Calculation**:
```
Success Rate = (applications with status='scoring_completed') / (total applications) × 100%
```

**Query Filter** (from `application_status_log` table logs):
```
log_source: "docker-hc-network" OR log_source: "kubernetes-pods"
AND json.status: "scoring_completed" OR json.status: "error"
```

**Visualization**: Single metric (green if >98%, yellow if 95-98%, red if <95%)

---

### 1.2 Requests Per Second (Line Chart)
**Metric**: Real-time throughput of incoming loan applications
**Source**: API Gateway access logs or PostgreSQL insert logs

**Query**:
```
kubernetes.namespace: "default"
AND kubernetes.pod.name: "api-gateway*"
AND json.method: "POST"
AND json.endpoint: "/loan-applications"
```

**Visualization**: Line chart with 1-minute intervals (last 30 minutes)
**Target**: Green zone >200 RPS, Yellow 100-200 RPS, Red <100 RPS

---

### 1.3 Applications Processed (Counter)
**Metric**: Total number of applications processed today
**Calculation**: Count of unique `sk_id_curr` with status >= 'submitted'

**Visualization**: Single metric counter (resets daily at midnight)

---

## Section 2: Pipeline Stage Performance

### 2.1 Stage Latency Breakdown (Horizontal Bar Chart)
**Metric**: Average time spent in each pipeline stage

**Stages to Track**:
1. **API → PostgreSQL Insert**: Time from request received to DB commit
2. **CDC Capture**: Time from PostgreSQL insert to Kafka topic
3. **Kafka → Flink**: Time from Kafka ingestion to Flink processing start
4. **Feature Engineering**: Flink processing time (bureau aggregation + external data join)
5. **Feast Retrieval**: Feature store lookup time
6. **KServe Inference**: Model prediction time
7. **Total End-to-End**: Sum of all stages

**Data Sources**:
- PostgreSQL logs: `INSERT INTO loan_applications` (timestamp)
- Debezium connector logs: CDC event timestamps
- Flink logs: Processing start/end timestamps
- KServe logs: Inference request/response timestamps

**Visualization**: Horizontal bar chart showing P50, P95, P99 latencies for each stage

---

### 2.2 Stage Success Rate (Donut Charts)
**Metric**: Success vs failure rate for each critical stage

**Stages**:
- **Pre-screening**: `pre_screening_passed` vs `pre_screening_failed`
- **Bureau API**: `bureau_received` vs `error` (with reason: bureau_timeout)
- **Feature Engineering**: `feature_engineering` completed vs errors
- **ML Scoring**: `scoring_completed` vs `error` (with reason: inference_failed)

**Query Example** (Pre-screening):
```
json.status: "pre_screening_passed" OR json.status: "pre_screening_failed"
```

**Visualization**: 4 donut charts side-by-side showing green (success) vs red (failure)

---

### 2.3 Pipeline Stage Flow (Sankey Diagram)
**Metric**: Application flow through pipeline stages with dropout visualization

**Flow**:
```
submitted (100%)
  → pre_screening_passed (98%)
    → bureau_received (97%)
      → feature_engineering (96%)
        → ml_scoring (95%)
          → scoring_completed (94%)
  → pre_screening_failed (2%)
  → error (1%)
```

**Visualization**: Sankey diagram showing volume at each stage and where applications drop out

---

## Section 3: Retry & Error Analysis

### 3.1 Retry Statistics (Table)
**Metric**: Number of retries by failure reason

**Columns**:
| Failure Reason | Retry Count | Success After Retry | Final Failure | Avg Retry Time |
|----------------|-------------|---------------------|---------------|----------------|
| Bureau API Timeout | 1,245 | 1,180 (94.8%) | 65 (5.2%) | 2.3s |
| Kafka Connection Error | 89 | 89 (100%) | 0 (0%) | 0.5s |
| Flink Processing Error | 34 | 30 (88.2%) | 4 (11.8%) | 1.8s |
| Feature Store Timeout | 12 | 10 (83.3%) | 2 (16.7%) | 1.2s |

**Data Source**:
```
json.metadata.retry_count: *
AND json.metadata.retry_reason: *
```

**Visualization**: Data table with sparkline showing retry trends over time

---

### 3.2 Retry Distribution (Histogram)
**Metric**: Distribution of retry attempts (0, 1, 2, ..., 15 attempts)

**X-axis**: Number of retry attempts (0-15)
**Y-axis**: Count of applications

**Query**:
```
json.metadata.retry_count: [0 TO 15]
```

**Visualization**: Vertical bar chart
**Expected Pattern**: Exponential decay (most applications succeed on first try)

---

### 3.3 Error Rate by Component (Stacked Area Chart)
**Metric**: Error count over time, broken down by component

**Components**:
- PostgreSQL (connection errors)
- Debezium CDC (capture errors)
- Kafka (produce/consume errors)
- Flink (processing errors)
- Feast (feature retrieval errors)
- KServe (inference errors)

**Query**:
```
json.level: "ERROR" OR json.level: "error"
AND json.component: *
```

**Visualization**: Stacked area chart (last 24 hours) showing which component contributes most errors

---

## Section 4: ML Model Performance

### 4.1 Approval Rate (Gauge)
**Metric**: Percentage of applications approved by ML model

**Calculation**:
```
Approval Rate = COUNT(status='approved') / COUNT(status IN ('approved','rejected')) × 100%
```

**Query**:
```
json.status: "approved" OR json.status: "rejected"
```

**Visualization**: Gauge chart (target range: 35-45% approval rate based on historical data)

---

### 4.2 Risk Score Distribution (Histogram)
**Metric**: Distribution of predicted default probabilities

**X-axis**: Risk score bins (0.0-0.1, 0.1-0.2, ..., 0.9-1.0)
**Y-axis**: Count of applications

**Data Source**:
```
json.metadata.risk_score: [0 TO 1.0]
```

**Visualization**: Histogram with color gradient (green=low risk, red=high risk)
**Overlay**: Approval threshold line (e.g., 0.5)

---

### 4.3 Model Inference Latency (Heatmap)
**Metric**: KServe inference latency over time

**X-axis**: Time of day (24 hours)
**Y-axis**: Day of week
**Color**: P95 latency (green <50ms, yellow 50-100ms, red >100ms)

**Query**:
```
kubernetes.namespace: "kserve"
AND json.inference_time_ms: *
```

**Visualization**: Heatmap showing when the model is slowest (helps identify resource contention)

---

### 4.4 Model Prediction Confidence (Box Plot)
**Metric**: Distribution of model confidence scores

**Data Source**:
```
json.metadata.confidence: *
```

**Visualization**: Box plot showing quartiles, median, outliers
**Use Case**: Identify applications sent to manual review (low confidence predictions)

---

## Section 5: Database & Connection Pool Health

### 5.1 PostgreSQL Connection Count (Line Chart)
**Metric**: Active connections to PostgreSQL over time

**Data Source**: PostgreSQL logs
```
json.message: "connection received" OR json.message: "connection authorized"
```

**Visualization**: Line chart with horizontal threshold lines:
- Green zone: <200 connections
- Yellow zone: 200-400 connections
- Red zone: >400 connections (approaching max_connections=500)

---

### 5.2 PgBouncer Pool Utilization (Area Chart)
**Metric**: Connection pool usage over time

**Query**:
```
container.name: "ops_pgbouncer"
AND json.pool_size: *
AND json.active_connections: *
```

**Calculation**:
```
Pool Utilization = (active_connections / pool_size) × 100%
```

**Visualization**: Area chart with alert threshold at 85% utilization

---

### 5.3 Database Query Performance (Top N Table)
**Metric**: Slowest queries in the last hour

**Columns**:
| Query Type | Avg Duration | P95 Duration | Count | Example |
|------------|--------------|--------------|-------|---------|
| INSERT loan_applications | 2ms | 8ms | 45,234 | INSERT INTO... |
| SELECT from application_status_log | 15ms | 45ms | 12,890 | SELECT status... |

**Query**:
```
json.query_duration_ms: [10 TO *]
```

**Visualization**: Data table sorted by P95 duration (descending)

---

## Section 6: Real-Time Alerts & Anomalies

### 6.1 Alert Timeline (Event Chart)
**Metric**: Critical events and alerts over time

**Event Types**:
- 🔴 **Pipeline Failure**: >5% error rate for 5+ minutes
- 🟡 **High Latency**: P95 end-to-end latency >3000ms
- 🟠 **Pool Saturation**: PgBouncer pool utilization >90%
- 🔵 **Model Degradation**: Approval rate drops >10% from baseline

**Visualization**: Timeline with colored event markers

---

### 6.2 Anomaly Detection (Line Chart with Bands)
**Metric**: Request volume with expected range bands

**Data**: Requests per minute
**ML Algorithm**: Use Kibana ML jobs to detect anomalies (unusual traffic patterns)

**Visualization**: Line chart with shaded confidence bands (gray) and anomaly markers (red dots)

---

## Section 7: User Experience Metrics

### 7.1 End-to-End Latency Percentiles (Line Chart)
**Metric**: P50, P95, P99 latency from API request to prediction result

**Calculation**:
```
Latency = timestamp(scoring_completed) - timestamp(submitted)
```

**Visualization**: Multi-line chart:
- Green line: P50 (median)
- Orange line: P95
- Red line: P99

**SLA Targets**:
- P50: <1000ms
- P95: <2000ms
- P99: <3000ms

---

### 7.2 Applications by Status (Stacked Bar Chart)
**Metric**: Current distribution of applications across pipeline stages

**Statuses**:
- Submitted
- Pre-screening
- Bureau Requested
- Feature Engineering
- ML Scoring
- Completed (Approved/Rejected)
- Error
- Manual Review

**Visualization**: Stacked horizontal bar showing current state of the system

---

### 7.3 Throughput vs Latency Scatter Plot
**Metric**: Relationship between system load and performance

**X-axis**: Requests per second (RPS)
**Y-axis**: P95 latency
**Color**: Time (gradient showing progression through the day)

**Use Case**: Identify performance degradation under load

---

## Section 8: Business Intelligence Metrics

### 8.1 Daily Application Volume (Bar Chart)
**Metric**: Total applications processed per day (last 30 days)

**Visualization**: Vertical bar chart with trend line

---

### 8.2 Approval Rate Trend (Line Chart)
**Metric**: Daily approval rate over the last 30 days

**Calculation**:
```
Daily Approval Rate = COUNT(approved) / COUNT(approved + rejected) × 100%
```

**Visualization**: Line chart with 7-day moving average overlay
**Alert**: If trend changes >5% over 7 days (potential model drift)

---

### 8.3 Revenue Impact (Calculated Metric)
**Metric**: Estimated loan value processed

**Calculation**:
```
Total Loan Value = SUM(json.amt_credit WHERE status='approved')
```

**Visualization**: Single metric with day-over-day percentage change

---

## Data Collection Requirements

### Structured Logging Format (JSON)

All services should emit logs in this format:

```json
{
  "timestamp": "2025-10-15T14:23:45.123Z",
  "level": "INFO",
  "component": "api-gateway",
  "event": "loan_application_received",
  "sk_id_curr": "CUSTOMER_12345",
  "status": "submitted",
  "metadata": {
    "request_id": "req_abc123",
    "user_ip": "192.168.1.100",
    "amt_credit": 50000.00,
    "processing_time_ms": 12
  }
}
```

### Key Fields for Each Component:

**PostgreSQL**:
```json
{
  "component": "postgresql",
  "event": "insert_completed",
  "sk_id_curr": "...",
  "query_duration_ms": 5,
  "connection_count": 156
}
```

**Debezium CDC**:
```json
{
  "component": "debezium-connector",
  "event": "cdc_captured",
  "sk_id_curr": "...",
  "capture_latency_ms": 45,
  "kafka_offset": 123456
}
```

**Kafka**:
```json
{
  "component": "kafka-producer",
  "event": "message_sent",
  "topic": "loan-applications",
  "partition": 0,
  "offset": 123456,
  "latency_ms": 8
}
```

**Flink**:
```json
{
  "component": "flink-feature-engineering",
  "event": "processing_completed",
  "sk_id_curr": "...",
  "processing_time_ms": 850,
  "features_count": 60,
  "cache_hit": true
}
```

**Feast**:
```json
{
  "component": "feast-feature-store",
  "event": "feature_retrieval",
  "sk_id_curr": "...",
  "retrieval_time_ms": 25,
  "features_retrieved": 150
}
```

**KServe**:
```json
{
  "component": "kserve-inference",
  "event": "prediction_completed",
  "sk_id_curr": "...",
  "inference_time_ms": 35,
  "risk_score": 0.342,
  "confidence": 0.89,
  "decision": "approved"
}
```

**Retry Logic** (any component):
```json
{
  "component": "...",
  "event": "retry_attempted",
  "sk_id_curr": "...",
  "retry_count": 2,
  "retry_reason": "bureau_api_timeout",
  "retry_success": true,
  "total_retry_time_ms": 2300
}
```

---

## Dashboard Layout (Grid Structure)

```
┌─────────────────────────────────────────────────────────────────┐
│ Section 1: Pipeline Success Rate & Throughput (Top KPIs)       │
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌────────────────────┐ │
│ │Success   │ │  RPS     │ │Apps      │ │ RPS Timeline       │ │
│ │ Rate     │ │  236     │ │Processed │ │ (line chart)       │ │
│ │  98.5%   │ │          │ │ 42,434   │ │                    │ │
│ └──────────┘ └──────────┘ └──────────┘ └────────────────────┘ │
├─────────────────────────────────────────────────────────────────┤
│ Section 2: Pipeline Stage Performance                          │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Stage Latency Breakdown (horizontal bar chart)            │  │
│ │ API→PostgreSQL:     ████ 2ms                              │  │
│ │ CDC Capture:        ███████ 45ms                          │  │
│ │ Kafka→Flink:        ████ 15ms                             │  │
│ │ Feature Engineering:████████████████ 850ms                │  │
│ │ Feast Retrieval:    ██████ 25ms                           │  │
│ │ KServe Inference:   ████ 35ms                             │  │
│ │ Total E2E:          ██████████████████████ 1200ms         │  │
│ └───────────────────────────────────────────────────────────┘  │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐             │
│ │Pre-     │ │Bureau   │ │Feature  │ │ML       │             │
│ │screening│ │API      │ │Engineer │ │Scoring  │             │
│ │ 98% ✓   │ │ 97% ✓   │ │ 96% ✓   │ │ 95% ✓   │             │
│ └─────────┘ └─────────┘ └─────────┘ └─────────┘             │
├─────────────────────────────────────────────────────────────────┤
│ Section 3: Retry & Error Analysis                              │
│ ┌────────────────────────┐ ┌──────────────────────────────┐   │
│ │ Retry Statistics Table │ │ Retry Distribution Histogram │   │
│ │ (showing top errors)   │ │ (attempts 0-15)              │   │
│ └────────────────────────┘ └──────────────────────────────┘   │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Error Rate by Component (stacked area chart)              │  │
│ └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│ Section 4: ML Model Performance                                │
│ ┌──────────┐ ┌─────────────────┐ ┌────────────────────────┐  │
│ │Approval  │ │ Risk Score      │ │ Inference Latency      │  │
│ │Rate      │ │ Distribution    │ │ Heatmap                │  │
│ │ 42%      │ │ (histogram)     │ │ (by hour/day)          │  │
│ └──────────┘ └─────────────────┘ └────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│ Section 5: Database & Connection Pool Health                   │
│ ┌────────────────────────┐ ┌──────────────────────────────┐   │
│ │ PostgreSQL Connections │ │ PgBouncer Pool Utilization   │   │
│ │ (line chart)           │ │ (area chart)                 │   │
│ └────────────────────────┘ └──────────────────────────────┘   │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Slowest Queries Table (top 10)                            │  │
│ └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│ Section 6: Real-Time Alerts & Anomalies                        │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Alert Timeline (event markers)                            │  │
│ └───────────────────────────────────────────────────────────┘  │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Anomaly Detection (line chart with bands)                 │  │
│ └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│ Section 7: User Experience Metrics                             │
│ ┌────────────────────────┐ ┌──────────────────────────────┐   │
│ │ E2E Latency Percentiles│ │ Applications by Status       │   │
│ │ (P50/P95/P99)          │ │ (stacked bar)                │   │
│ └────────────────────────┘ └──────────────────────────────┘   │
│ ┌───────────────────────────────────────────────────────────┐  │
│ │ Throughput vs Latency Scatter Plot                        │  │
│ └───────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│ Section 8: Business Intelligence Metrics                       │
│ ┌──────────┐ ┌─────────────────┐ ┌────────────────────────┐  │
│ │Daily     │ │ Approval Rate   │ │ Revenue Impact         │  │
│ │App Volume│ │ Trend (30d)     │ │ (loan value)           │  │
│ └──────────┘ └─────────────────┘ └────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Implementation Checklist

### Phase 1: Data Collection (Week 1)
- [ ] Add structured JSON logging to all services
- [ ] Verify Filebeat is capturing all logs (Docker + K8s)
- [ ] Confirm logs appear in Elasticsearch indices
- [ ] Create index patterns in Kibana:
  - `filebeat-docker-*` (Docker containers)
  - `filebeat-8.5.1` (Kubernetes pods)

### Phase 2: Basic Metrics (Week 2)
- [ ] Create Section 1: Top KPIs (success rate, RPS, counter)
- [ ] Create Section 2: Stage performance (latency breakdown)
- [ ] Create Section 5: Database health (connection counts)

### Phase 3: Advanced Analytics (Week 3)
- [ ] Create Section 3: Retry & error analysis
- [ ] Create Section 4: ML model performance
- [ ] Create Section 7: User experience metrics

### Phase 4: Alerting & Business Metrics (Week 4)
- [ ] Create Section 6: Real-time alerts & anomalies
- [ ] Create Section 8: Business intelligence metrics
- [ ] Configure Kibana alerting rules (Slack/email notifications)

---

## Kibana Query Examples

### Query 1: Calculate End-to-End Latency
```
GET /filebeat-*/_search
{
  "query": {
    "bool": {
      "must": [
        { "match": { "json.sk_id_curr": "CUSTOMER_12345" }},
        { "terms": { "json.status": ["submitted", "scoring_completed"] }}
      ]
    }
  },
  "sort": [{ "@timestamp": "asc" }]
}
```

### Query 2: Count Retries by Reason
```
GET /filebeat-*/_search
{
  "size": 0,
  "query": { "exists": { "field": "json.metadata.retry_count" }},
  "aggs": {
    "retry_reasons": {
      "terms": { "field": "json.metadata.retry_reason.keyword" },
      "aggs": {
        "avg_retry_count": { "avg": { "field": "json.metadata.retry_count" }},
        "success_rate": {
          "filter": { "term": { "json.metadata.retry_success": true }}
        }
      }
    }
  }
}
```

### Query 3: Top 10 Slowest Pipeline Stages
```
GET /filebeat-*/_search
{
  "size": 0,
  "query": { "exists": { "field": "json.processing_time_ms" }},
  "aggs": {
    "by_component": {
      "terms": {
        "field": "json.component.keyword",
        "size": 10
      },
      "aggs": {
        "avg_latency": { "avg": { "field": "json.processing_time_ms" }},
        "p95_latency": { "percentiles": { "field": "json.processing_time_ms", "percents": [95] }},
        "p99_latency": { "percentiles": { "field": "json.processing_time_ms", "percents": [99] }}
      }
    }
  }
}
```

---

## Performance Targets (SLAs)

| Metric | Target | Warning | Critical |
|--------|--------|---------|----------|
| **Overall Success Rate** | >98% | <98% | <95% |
| **P95 End-to-End Latency** | <2000ms | >2000ms | >3000ms |
| **Requests Per Second** | 200+ | <100 | <50 |
| **Approval Rate** | 35-45% | <30% or >50% | <25% or >55% |
| **PostgreSQL Connections** | <300 | >400 | >450 |
| **PgBouncer Pool Utilization** | <80% | >85% | >90% |
| **Retry Success Rate** | >95% | <95% | <90% |
| **Feature Engineering Latency** | <1000ms | >1500ms | >2000ms |
| **Model Inference Latency** | <50ms | >100ms | >200ms |

---

## Alert Rules Configuration

### Critical Alerts (Slack + PagerDuty)
1. **Pipeline Failure**: Success rate <95% for 5+ minutes
2. **High Error Rate**: >5% errors for 10+ minutes
3. **Connection Pool Exhaustion**: PgBouncer utilization >90%
4. **Database Overload**: PostgreSQL connections >450

### Warning Alerts (Slack only)
1. **High Latency**: P95 E2E latency >2500ms for 15+ minutes
2. **Model Drift**: Approval rate changes >10% from 7-day baseline
3. **Retry Surge**: Retry count >1000/hour
4. **Slow Feature Engineering**: Flink P95 latency >1500ms

---

## Next Steps

1. **Implement structured logging** across all services (use the JSON format above)
2. **Verify Filebeat collection** for both Docker containers and K8s pods
3. **Create Kibana index patterns** and verify data visibility
4. **Build dashboard sections** incrementally (start with Section 1 KPIs)
5. **Configure alerting rules** for critical metrics
6. **Train team** on dashboard usage and alert response procedures

---

## References

- EFK Stack Setup: `services/ops/k8s/logging/README.md`
- Database Schema: `services/core/schemas/002_create_application_status_log.sql`
- Performance Results: `reports/FINAL_PERFORMANCE_RESULTS.md`
- Hardware Specifications: `reports/HARDWARE_SPECIFICATIONS.md`
