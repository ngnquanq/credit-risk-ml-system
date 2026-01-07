# Kibana Real-Time Dashboard Capabilities & Limitations

**Quick Answer**: Kibana provides **near real-time** dashboards (1-5 second refresh), **NOT true real-time** (sub-second streaming updates).

---

## How "Real-Time" is Kibana?

### ✅ What Kibana CAN Do (Near Real-Time)

1. **Auto-Refresh Dashboards**:
   - Minimum refresh interval: **1 second** (configurable: 5s, 10s, 30s, 1m, 5m, 15m)
   - Dashboard re-queries Elasticsearch at each interval
   - Typical latency: **1-5 seconds** from log generation to dashboard display

2. **Data Pipeline Latency**:
   ```
   Application Log → Filebeat (1s) → Elasticsearch (1-2s) → Kibana Query (1s) = 3-4s total
   ```

3. **Real-Time Use Cases Kibana Handles Well**:
   - Monitoring request rates (RPS) with 5-10 second accuracy
   - Tracking error spikes (alerts trigger within 1-2 minutes)
   - Observing pipeline stage performance trends
   - Detecting anomalies within 1-5 minutes

### ❌ What Kibana CANNOT Do (True Real-Time)

1. **Sub-Second Updates**:
   - Cannot update every 100ms or 500ms
   - Not suitable for tick-by-tick trading systems or gaming leaderboards

2. **Live Streaming Visualizations**:
   - Each "refresh" re-queries the entire dataset (not a live stream)
   - Does not use WebSocket push notifications

3. **True Event-Driven Updates**:
   - Dashboard doesn't update immediately when a log arrives
   - Waits for next refresh interval

---

## Kibana Refresh Mechanism

### How Auto-Refresh Works

```javascript
// Kibana auto-refresh behavior (simplified)
setInterval(() => {
  // 1. Re-execute all dashboard queries
  const results = await elasticsearch.search(query);

  // 2. Re-render all visualizations
  updateCharts(results);
}, refreshInterval); // Minimum: 1000ms (1 second)
```

**Key Point**: This is **polling**, not **streaming**. Kibana repeatedly asks "what's new?" rather than being pushed updates.

---

## Performance Impact of Auto-Refresh

### Elasticsearch Query Load

**Example**: Dashboard with 20 visualizations, 1-second refresh
- **Queries per minute**: 20 panels × 60 refreshes = **1,200 queries/minute**
- **Queries per hour**: 72,000 queries/hour from a single dashboard viewer

**Recommendation**:
- Development/monitoring: **5-10 second** refresh (balanced)
- Alerting dashboards: **30 second - 1 minute** refresh (reduces load)
- Historical analysis: **Manual refresh only** (no auto-refresh)

### Elasticsearch Load for Your System

With your current load (236 RPS sustained, 502 RPS peak):
- **Ingestion rate**: ~15,000 logs/minute (estimating 5-10 logs per application)
- **Dashboard queries**: ~1,200 queries/minute (20 panels × 1s refresh)
- **Query-to-ingestion ratio**: ~8% overhead (acceptable)

**Verdict**: Your single-node Elasticsearch (10Gi, 30920 port) can handle 5-10 second dashboard refresh for 5-10 concurrent viewers.

---

## Alternatives for True Real-Time Dashboards

If you need **sub-second real-time** updates (100-500ms), consider these alternatives:

### Option 1: Grafana + Prometheus (Recommended for ML Systems)

**Why Better for Real-Time**:
- **Pull-based metrics** with 1-second scrape intervals
- **PromQL queries** execute faster than Elasticsearch aggregations
- **Streaming architecture** with efficient time-series storage

**Setup**:
```yaml
# Prometheus scrapes metrics every 1 second
scrape_configs:
  - job_name: 'ml-pipeline'
    scrape_interval: 1s  # Faster than Kibana's 1s refresh
    static_configs:
      - targets: ['api-gateway:9090', 'kserve:9090']
```

**Grafana Auto-Refresh**: 100ms - 1s (smoother than Kibana)

**Migration Path**: You already have Grafana deployed (`docker-compose.grafana.yml`)!

---

### Option 2: Custom Real-Time Dashboard (WebSocket)

**Architecture**:
```
Application → Kafka → WebSocket Server → Browser (SSE/WebSocket)
                                       ↓
                                  Real-time Chart (D3.js, Chart.js)
```

**Latency**: 50-200ms (true real-time)

**Use Cases**:
- Live RPS counter (updates every 100ms)
- Real-time error stream (shows errors as they happen)
- Live application status board

**Complexity**: High (requires custom development)

---

### Option 3: Kibana + Watcher (Alert-Based)

**For Critical Events Only**:
- Use **Kibana Alerting** or **Elasticsearch Watcher** for instant notifications
- Alerts fire within 1-10 seconds of condition being met
- Sends to Slack/PagerDuty immediately

**Example**:
```json
{
  "trigger": {
    "schedule": { "interval": "10s" }
  },
  "input": {
    "search": {
      "request": {
        "indices": ["filebeat-*"],
        "body": {
          "query": { "match": { "json.level": "ERROR" }},
          "aggs": { "error_count": { "value_count": { "field": "_id" }}}
        }
      }
    }
  },
  "condition": {
    "compare": { "ctx.payload.aggregations.error_count.value": { "gt": 10 }}
  },
  "actions": {
    "notify_slack": {
      "webhook": {
        "url": "https://hooks.slack.com/...",
        "body": "🚨 ERROR SPIKE: {{ctx.payload.aggregations.error_count.value}} errors in last 10s"
      }
    }
  }
}
```

**Response Time**: 10-30 seconds (acceptable for alerting)

---

## Recommended Architecture for Your System

### Hybrid Approach: Kibana + Grafana + Alerts

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: REAL-TIME METRICS (Grafana + Prometheus)          │
│ - RPS (updated every 1s)                                    │
│ - Active connections (updated every 1s)                     │
│ - Latency P50/P95/P99 (updated every 5s)                   │
│ - Database query rate (updated every 1s)                    │
│ Refresh: 1-5 seconds, Low query overhead                   │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: NEAR REAL-TIME LOGS (Kibana + Elasticsearch)      │
│ - Pipeline stage success/failure (updated every 10s)       │
│ - Retry analysis (updated every 30s)                        │
│ - Error log stream (updated every 5s)                       │
│ - Full-text log search (on-demand)                          │
│ Refresh: 5-30 seconds, Rich log context                    │
└─────────────────────────────────────────────────────────────┘
                            ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: INSTANT ALERTS (Prometheus Alertmanager)          │
│ - Success rate <95% → Slack + PagerDuty (10s latency)     │
│ - Connection pool >90% → Slack (10s latency)              │
│ - Error spike >10/min → Slack (10s latency)               │
│ Response: 10-30 seconds, Proactive notification            │
└─────────────────────────────────────────────────────────────┘
```

---

## Detailed Comparison Table

| Feature | Kibana + Elasticsearch | Grafana + Prometheus | Custom WebSocket Dashboard |
|---------|------------------------|----------------------|----------------------------|
| **Minimum Refresh** | 1 second | 100ms - 1s | 50-200ms (true real-time) |
| **Query Mechanism** | Polling (re-query) | Polling (scrape) | Streaming (push) |
| **Best For** | Log analysis, full-text search | Metrics, time-series | Live counters, event streams |
| **Data Retention** | Days to weeks (high storage) | Weeks to months (efficient) | Minutes to hours (ephemeral) |
| **Query Complexity** | High (JSON aggregations) | Medium (PromQL) | Low (simple calculations) |
| **Elasticsearch Load** | High (1200 queries/min) | None | None |
| **Setup Complexity** | Low (already deployed) | Medium (need exporters) | High (custom code) |
| **Log Context** | ✅ Full log text | ❌ Metrics only | ❌ Metrics only |
| **Alerting** | ✅ Built-in | ✅ Excellent (Alertmanager) | ❌ Manual implementation |
| **Cost** | Moderate (storage) | Low (time-series compression) | Low (stateless) |

---

## Kibana Real-Time Configuration for Your Dashboard

### Recommended Refresh Intervals by Section

```yaml
# Section 1: Pipeline Success Rate & Throughput (Top KPIs)
refresh: 5s  # Balance between real-time feel and query load

# Section 2: Pipeline Stage Performance
refresh: 10s  # Latency metrics don't need sub-5s updates

# Section 3: Retry & Error Analysis
refresh: 30s  # Historical analysis, not urgent

# Section 4: ML Model Performance
refresh: 1m  # Model metrics change slowly

# Section 5: Database & Connection Pool Health
refresh: 5s  # Critical for operational alerting

# Section 6: Real-Time Alerts & Anomalies
refresh: 10s  # Alert timeline

# Section 7: User Experience Metrics
refresh: 10s  # UX metrics

# Section 8: Business Intelligence Metrics
refresh: 5m  # Business metrics change slowly
```

### Elasticsearch Index Refresh Interval

**Default**: 1 second (Elasticsearch refreshes indices every 1s to make new docs searchable)

**Tune for Performance**:
```json
PUT /filebeat-docker-*/_settings
{
  "index.refresh_interval": "5s"
}
```

**Trade-off**:
- Lower refresh = better search performance, slower data visibility
- Higher refresh = more real-time data, higher indexing overhead

**Recommendation**: Keep default **1 second** for your workload (236 RPS ingestion is low for Elasticsearch).

---

## Actual Latency Breakdown (For Your System)

### From Application Event to Kibana Dashboard

```
Application logs event (t=0ms)
    ↓
Filebeat reads log file (t=0-1000ms, 1s polling interval)
    ↓
Filebeat batches and sends to Elasticsearch (t=100-500ms, network + batch)
    ↓
Elasticsearch indexes document (t=50-200ms, write + refresh)
    ↓
Kibana dashboard refresh fires (t=0-5000ms, depends on refresh interval)
    ↓
Elasticsearch executes aggregation query (t=50-500ms, depends on query complexity)
    ↓
Kibana renders visualization (t=50-200ms, browser rendering)
    ↓
Total: 1,250ms - 7,400ms (1.3s - 7.4s from log to screen)
```

**Best Case** (1s refresh, simple query): ~1.3 seconds
**Worst Case** (5s refresh, complex aggregation): ~7.4 seconds

---

## Practical Recommendations for Your Dashboard

### 1. **Use 5-10 Second Refresh for Operations Dashboard**

**Why**:
- Good balance between "real-time feel" and Elasticsearch load
- Operators don't need sub-second updates for troubleshooting
- Your system already has 1-2 second latency (Kafka → Flink → KServe), so 5s refresh is acceptable

**Example**:
```
Time Range: Last 15 minutes
Auto-refresh: Every 5 seconds
Expected lag: 5-10 seconds behind actual events
```

### 2. **Migrate Critical Metrics to Grafana + Prometheus**

**Metrics to Move**:
- RPS (needs 1s updates)
- PostgreSQL connection count (needs 1s updates)
- PgBouncer pool utilization (needs 1s updates)
- P95 latency (needs 5s updates)

**Why**:
- Prometheus scrapes `/metrics` endpoints every 1 second
- Grafana refreshes every 1 second with minimal overhead
- Better for operational alerting (Prometheus Alertmanager is faster than Kibana Watcher)

### 3. **Use Kibana for Log Analysis, Not Live Metrics**

**Keep in Kibana**:
- Error log exploration (full-text search)
- Retry analysis (complex aggregations)
- Pipeline stage debugging (log correlation across services)
- Historical trend analysis (last 7-30 days)

**Why**:
- Kibana excels at log exploration with Lucene queries
- Elasticsearch aggregations handle complex retry/error analysis better than PromQL

### 4. **Implement Instant Alerts (Don't Rely on Dashboard Refresh)**

**Use Kibana Alerting** for:
- Success rate <95% → Check every 1 minute, alert if condition persists for 5 minutes
- Error spike >10/min → Check every 10 seconds, alert immediately
- Connection pool >90% → Check every 10 seconds, alert if condition persists for 1 minute

**Why**:
- Alerts run independently of dashboard refresh
- Faster response time (10-60 seconds vs 5-10 minutes if relying on dashboard)

---

## Conclusion: Is Kibana Real-Time Enough?

### ✅ YES for Your Use Case

**Your Requirements**:
- Monitor prediction pipeline performance
- Track success/failure rates
- Analyze retry patterns
- Observe approval rates

**Kibana Capabilities**:
- 5-10 second refresh is sufficient for operational monitoring
- Error spikes detected within 30-60 seconds (acceptable)
- Historical log analysis is excellent

### ⚠️ Consider Grafana for These Metrics

**If You Need**:
- Live RPS counter (updates every 1 second)
- Real-time connection pool monitoring (updates every 1 second)
- Sub-5 second alerting for critical metrics

**Then**:
- Export metrics to Prometheus (add `/metrics` endpoints to services)
- Create Grafana dashboard for operational metrics
- Keep Kibana for log exploration and complex analysis

---

## Next Steps

1. **Start with Kibana 5-second refresh** for your dashboard (good enough for 90% of use cases)
2. **Monitor Elasticsearch query load** using Kibana Stack Monitoring
3. **If you hit performance issues** (slow queries, high CPU), consider:
   - Increase refresh interval to 10-30 seconds
   - Reduce number of visualizations per dashboard
   - Migrate time-series metrics to Grafana + Prometheus
4. **Implement Kibana Alerting** for instant notifications (don't rely on dashboard refresh for alerts)

---

## References

- Kibana Auto-Refresh: https://www.elastic.co/guide/en/kibana/current/set-time-filter.html#auto-refresh
- Elasticsearch Refresh Interval: https://www.elastic.co/guide/en/elasticsearch/reference/current/indices-update-settings.html
- Prometheus vs Elasticsearch: https://prometheus.io/docs/introduction/comparison/
- Your EFK Setup: `services/ops/k8s/logging/README.md`
- Your Grafana Setup: `services/ops/docker-compose.monitoring.yml`
