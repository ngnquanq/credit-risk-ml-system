# Feast Feature Store Architecture Guide

> **Purpose**: This document explains how our Feast feature store works, what each file does, and how data flows through the system for real-time credit risk scoring.

## 🏗️ **System Overview**

Our Feast feature store implements a **Lambda architecture** that enables real-time credit risk decisions by materializing streaming features from Kafka into Redis for sub-millisecond lookups during loan scoring.

### **High-Level Data Flow**
```
Raw Credit Data → Kafka Topics → Feast Stream Processor → Redis → BentoML Scoring Service
                     ↓
               Feature Definitions → Feast Registry → Feature Lookups
```

---

## 📂 **File Architecture & Purpose**

### **🔧 Core Configuration Files**

#### `feature_store.yaml`
- What it does: Main Feast configuration file
- Contents: Redis connection (`redis://feast_redis:6379/0`), project `hc`, registry `data/registry.db`
- Why it matters: Feast reads this to know where to store and retrieve features

#### `generate_config.py`
- **What it does**: Dynamically creates `feature_store.yaml` from environment variables
- **Why it's important**: Enables different configurations for dev/staging/production
- **When to use**: Run before deploying to ensure environment-specific settings
- **Key env vars**: `FEAST_REDIS_URL`, `FEAST_PROJECT`, `FEAST_REGISTRY_PATH`

### **📋 Schema Definition Files**

#### `entities.py`
- **What it does**: Defines the `customer` entity with `sk_id_curr` as the join key
- **Purpose**: Tells Feast how to group features by customer ID
- **Simple but critical**: All features must be linked to this entity

#### `feature_views.py` ⭐ **CORE FILE**
- **What it does**: Defines 6 feature views (3 streaming + 3 batch)
- **Data sources**: 
  - **Application features** (58 fields) ← Flink pipeline
  - **External/Bureau features** (60 fields) ← Credit bureau service  
  - **DWH features** (dynamic count) ← ClickHouse aggregations
- **Why dual views**: Compatibility across Feast versions and different use cases
- **TTL settings**: 1 day for application data, 7 days for external/DWH data

#### `dwh_schema.py`
- **What it does**: Automatically discovers DWH feature schema from ClickHouse
- **Why it's smart**: Avoids manually maintaining 100+ feature definitions
- **Data sources**: `mart_credit_card_balance`, `mart_pos_cash_balance`, `mart_previous_application`
- **Fallback**: Provides minimal schema if ClickHouse is unavailable

### **🎯 Service Orchestration Files**

#### `feature_services.py`
- **What it does**: Bundles all features into `realtime_scoring_v1` service
- **Purpose**: Provides a single interface for the ML model to request all needed features
- **Usage**: Referenced in BentoML service configuration

#### `repository.py` ⭐ **ORCHESTRATOR**
- **What it does**: Central command center that applies all definitions to Feast
- **Key functions**:
  - `apply()`: Registers all entities, feature views, and services
  - `start_stream_processor()`: Launches the streaming pipeline
- **When to run**: After any schema changes or initial setup
- **Creates**: Dummy parquet files for batch sources (Feast requirement)

#### `stream_processor.py` ⭐ **STREAM MATERIALIZER**
- **What it does**: The engine that moves data from Kafka → Redis
- **Kafka topics consumed**:
  - `hc.application_features` (from Flink)
  - `hc.application_ext` (from external service)
  - `hc.application_dwh` (from DWH service)
- **Process**: Extracts `sk_id_curr` + features, writes to Redis with timestamps
- **Resilience**: Auto-reconnects, handles CDC format, graceful error handling

### **📚 Documentation & Data**

#### `README.md`
- **What it does**: Basic setup and usage instructions
- **Audience**: Quick reference for developers

#### `data/registry.db`
- **What it does**: SQLite database storing Feast metadata
- **Contents**: Feature view definitions, entity schemas, service configurations
- **Important**: This file tracks your feature store state

---

## 🔄 **Data Sources Deep Dive**

### **1. Application Features Stream** 
**Topic**: `hc.application_features`  
**Source**: Flink real-time pipeline  
**Freshness**: TTL 1 day  
**Purpose**: Core loan application data for immediate scoring

**Key Feature Categories**:
- Demographics: `cnt_children`, `amt_income_total`
- Loan specifics: `amt_credit`, `amt_annuity`, `amt_goods_price`
- Employment: `days_employed`, `organization_type`
- Verification: 21 document flags (`flag_document_2` through `flag_document_21`)

### **2. External/Bureau Features Stream**
**Topic**: `hc.application_ext`  
**Source**: External credit bureau service  
**Freshness**: TTL 7 days  
**Purpose**: Credit history and external risk assessment

**Key Feature Categories**:
- External scores: `ext_source_1`, `ext_source_2`, `ext_source_3`
- Bureau analytics: Overdue patterns, debt ratios, utilization metrics
- Risk indicators: Payment history, credit behavior patterns
- Comprehensive credit profile: 60 engineered features from bureau data

### **3. Data Warehouse Features Stream**
**Topic**: `hc.application_dwh`  
**Source**: ClickHouse DWH aggregations  
**Freshness**: TTL 7 days  
**Purpose**: Historical patterns and derived metrics

**Dynamic Schema**: Features are auto-discovered from:
- `mart_credit_card_balance`: Credit card usage patterns
- `mart_pos_cash_balance`: Point-of-sale credit behavior  
- `mart_previous_application`: Historical loan application patterns

---

## 🚀 **Operational Guidance**

### **Initial Setup**
1. Start dependencies: Redis (`feast_redis:6379`), Kafka, ClickHouse
2. **Apply schema**: `cd application/feast && python repository.py`
3. **Start stream processor**: `python repository.py stream`
4. **Verify**: Check Redis for feature keys, monitor logs

### **Making Schema Changes**
1. **Modify**: Update `feature_views.py` or `dwh_schema.py`
2. **Re-apply**: Run `python repository.py` to update registry
3. **Restart streams**: Restart `stream_processor.py` to pick up changes
4. **Test**: Verify BentoML can retrieve updated features

### **Monitoring & Troubleshooting**

#### **Common Issues**:
- **"No features found"**: Check if stream processor is running and consuming topics
- **Redis connection errors**: Verify `FEAST_REDIS_URL` and Redis availability
- **Schema mismatches**: Re-run `repository.py` after feature definition changes
- **Working directory errors**: Use absolute paths (already fixed in BentoML config)

#### **Health Checks**:
- **Registry**: Check `data/registry.db` size and modification time
- **Redis**: Use `redis-cli` to inspect feature keys
- **Kafka**: Monitor topic consumption lag
- **ClickHouse**: Verify DWH tables are accessible

### **Environment Configuration**

#### **Required Environment Variables**:
```bash
# Feast Configuration
FEAST_REDIS_URL=redis://feast_redis:6379/0
FEAST_KAFKA_BROKERS=localhost:9092
FEAST_PROJECT=hc
FEAST_REGISTRY_PATH=data/registry.db

# ClickHouse (for DWH schema inference)
APP_CLICKHOUSE_HOST=localhost
APP_CLICKHOUSE_PORT=8123
APP_CLICKHOUSE_DB_DWH=application_mart

# Topic Configuration
FEAST_TOPIC_APP_FEATURES=hc.application_features
FEAST_TOPIC_EXTERNAL=hc.application_ext
FEAST_TOPIC_DWH=hc.application_dwh
```

---

## 🎯 **Integration with BentoML**

### **Feature Retrieval Pattern**:
```python
from feast import FeatureStore

# Initialize (uses absolute path - no more working directory issues!)
fs = FeatureStore(repo_path=settings.feast_repo_path)

# Retrieve features for scoring
features = fs.get_online_features(
    features=[
        "application_features:cnt_children",
        "application_features:amt_income_total", 
        "external_features:ext_source_1",
        "dwh_features:agg_prev_loans"
    ],
    entity_rows=[{"sk_id_curr": customer_id}]
).to_dict()
```

### **Feature Mapping**: 
The BentoML service in `application/scoring/service.py` maps Feast feature names to ML model column names using the `_map_feast_features()` function.

---

## ⚡ **Performance Characteristics**

- **Lookup Latency**: Sub-millisecond (Redis)
- **Feature Freshness**: 1-7 days TTL
- **Throughput**: Handles real-time Kafka streams
- **Reliability**: Auto-reconnection, graceful degradation
- **Scalability**: Horizontal scaling via Kafka partitions

---

## 🔒 **Security Considerations**

- **Redis**: No authentication in dev (configure for production)
- **Kafka**: PLAINTEXT in dev (use SASL/SSL for production)
- **ClickHouse**: Default user access (restrict in production)
- **Feature Access**: All features exposed via single service (consider feature-level ACLs)

---

## 📝 **Summary**

This Feast setup provides a **production-ready feature store** that:
- ✅ Ingests from 3 real-time data sources
- ✅ Maintains 100+ features with automatic schema management  
- ✅ Provides sub-millisecond lookups for ML inference
- ✅ Handles version compatibility and operational concerns
- ✅ Integrates seamlessly with the BentoML scoring service

**No files are redundant** - each serves a specific purpose in the streaming feature pipeline that powers real-time credit risk decisions.
