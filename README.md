# Home Credit — Credit Risk Model Stability

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-green.svg)](https://python.org)
[![K8s](https://img.shields.io/badge/platform-Kubernetes-326CE5.svg)](https://kubernetes.io)

End-to-end credit risk decisioning platform — from loan application to automated approve/reject decision. 100% automated, real-time scoring via Kafka + Redis + KServe, targeting ~140 RPS with sub-10-minute end-to-end SLA.

## Results

| Metric | Value |
|--------|-------|
| **AUC (ROC)** | ~0.77 |
| **Accuracy @ threshold 0.3** | ~0.77 |
| **Features** | 24 (19 numeric + 5 categorical) |
| **Model** | XGBoost (300 trees, depth 4, lr 0.05) |
| **Dataset** | 307,511 loan applications (8.1% default rate) |
| **Throughput** | 120–150 RPS at 200 concurrent users |

AUC was chosen over accuracy due to the class imbalance (91.9% repay / 8.1% default). See [`notebook/model_evaluation.ipynb`](notebook/model_evaluation.ipynb) for ROC curves, precision-recall, calibration, and threshold tradeoff analysis. See [`MODEL_CARD.md`](MODEL_CARD.md) for full model documentation.

## Quick Start (ML-only)

If you just want to explore the model and notebooks without deploying the full K8s stack:

```bash
# Install dependencies
pip install -r requirements.txt

# Train and evaluate the model
python application/training/train_register.py \
    --data data/complete_feature_dataset.csv \
    --experiment credit-risk \
    --register-name credit_risk_model

# Run evaluation notebooks
jupyter notebook notebook/model_evaluation.ipynb
jupyter notebook notebook/feature_importance.ipynb
```

## Project Structure

```
.
├── application/                  # Application code
│   ├── core/                     #   Config, settings
│   ├── domain/                   #   Business logic & entities
│   ├── entrypoints/              #   FastAPI + Streamlit UIs
│   ├── feast/                    #   Feast feature definitions
│   ├── infrastructure/           #   DB clients, Kafka, external APIs
│   ├── scoring/                  #   BentoML scoring service
│   ├── training/                 #   Training scripts (XGBoost, Spark)
│   └── workflows/                #   Kubeflow pipeline definitions
├── platform/                     # Infrastructure-as-code
│   ├── core/                     #   Core infra (Postgres, PgBouncer)
│   ├── data/                     #   Data platform K8s manifests
│   │   └── k8s/                  #     Kafka, ClickHouse, Flink, CDC, MinIO
│   ├── ml/                       #   ML platform K8s manifests
│   │   └── k8s/                  #     KServe, MLflow, Kubeflow, Feast, Ray
│   └── ops/                      #   Observability & scripts
│       └── k8s/                  #     Prometheus, Grafana, ECK
├── tests/                        # Test suite (194 tests, 25 files)
│   ├── unit/                     #   Unit tests
│   ├── integration/              #   Integration tests
│   └── test_load/                #   Locust load tests
├── notebook/                     # Jupyter notebooks (EDA, modeling, evaluation)
├── ml_data_mart/                 # dbt models for ClickHouse
├── Makefile                      # Orchestration targets
├── MODEL_CARD.md                 # Model documentation
└── LICENSE                       # MIT License
```

## System Architecture

**Data flow**: Postgres → Debezium/Kafka → Flink → Redis/ClickHouse → KServe/BentoML → Kafka

- **Data platform**: PostgreSQL (operational DB) + Debezium (CDC) → Kafka → Flink → ClickHouse (DWH) + Redis (online store)
- **ML platform**: Kubeflow/Ray (training) → MLflow (registry) → BentoML (bundling) → KServe (serving)
- **Feature store**: Feast with offline (ClickHouse) and online (Redis) stores, Flink materialization
- **Observability**: Prometheus + Grafana (metrics), ECK — Elasticsearch + Kibana + Filebeat (logs)
- **Model deployment pipeline**: MLflow watcher detects promotion → builds Bento bundle → serving watcher deploys KServe InferenceService (blue-green or canary)

## Full Stack Deployment

**Prerequisites**: Docker, kubectl, Minikube 1.32+, Helm 3, Python 3.10+, 32 GB RAM minimum.

### 1. Cluster & Core Data Platform

```bash
make k8s-up                      # Start Minikube (mlops profile)
make k8s-core                    # Postgres, Kafka, ClickHouse, MinIO, API Gateway
make k8s-kafka-topics            # Create required Kafka topics
make k8s-streaming               # Flink stream processing
make k8s-load-dwh                # Load CSVs into ClickHouse + dbt transforms
```

### 2. ML Platform

```bash
make k8s-training-data-storage   # Dedicated MinIO for training snapshots
make k8s-export-training-snapshot
make k8s-kubeflow                # Kubeflow Pipelines
make k8s-ray                     # Ray cluster (distributed tuning)
make k8s-model-registry          # MLflow + Postgres + MinIO
make k8s-knative-complete        # KServe + Knative (Serving + Eventing + Kafka)
make k8s-mlflow-watcher          # Auto-trigger Bento builds on model promotion
make k8s-model-serving           # Bundle storage + serving watcher
make k8s-feature-registry        # Feast + Redis online store
```

### 3. Observability

```bash
make k8s-monitoring              # Prometheus + Grafana + cAdvisor
make k8s-logging                 # ECK (Elasticsearch + Kibana + Filebeat)
```

### 4. Port Forwards

```bash
make pf-clickhouse               # localhost:8123
make pf-mlflow                   # localhost:5000
make pf-minio-training           # localhost:9000 (API) + localhost:9090 (Console)
make pf-kafka-ui                 # localhost:8080
```

### Model Flow

Train & log to MLflow → mlflow-watcher builds Bento bundle → bundle stored in MinIO → serving-watcher deploys KServe InferenceService → scoring pods consume Kafka and use Redis features.

## Performance Optimization Log

Three iterations of load testing (200 concurrent users, 5 user/sec ramp-up, 10 min) drove major architectural improvements:

### Iteration 1 — Baseline
- **Result**: 120–130 RPS, p95 latency ~7 min
- **Root cause**: Serialized Feast lookups in serving pod — each thread blocked up to 4.5s retrying feature availability
- **Fix**: Replaced polling with Kafka event-driven pattern (`hc.feature_ready` topic) to enable parallel processing

### Iteration 2 — Post-Kafka Refactor
- **Result**: 80–120 RPS, p95 improved by ~100s
- **Root cause**: (1) XGBoost using all CPU cores per prediction, causing context-switch overhead; (2) Redis write throughput saturated during Feast materialization
- **Fix**: Configured inference thread count; horizontal Redis scaling

### Iteration 3 — Micro-batch + Resource Tuning
- **Result**: 120–150 RPS (stable ~140), p95 reduced to ~350s
- **Improvements**: Micro-batch Redis ingestion (200 records or 300ms window), tuned worker/thread/pod counts and resource limits
- **Remaining**: Fan-out serving pods beyond partition count with load balancer

## Testing

```bash
# Run all tests (194 tests across 25 files)
PYTHONPATH=application pytest tests/ --ignore=tests/test_load -v

# Load test (requires running infrastructure)
locust -f tests/test_load/locustfile_e2e_prediction.py --web-host=0.0.0.0 --web-port=8089
```

## Operations

- **Restart after Minikube IP change**: `minikube -p mlops stop && make k8s-up`
- **Clean start**: `minikube delete -p mlops` then `make k8s-up`
- **Rebuild serving after model promotion**: Ensure mlflow-watcher and serving-watcher are running
- **Feature backfill**: Check Feast repo for materialization job definitions

## Dataset

[Home Credit Default Risk](https://www.kaggle.com/c/home-credit-default-risk) (Kaggle, ~3 GB). External bureau + internal loan history data. See `notebook/` for EDA.

## Notebooks

| Notebook | Description |
|----------|-------------|
| `model_evaluation.ipynb` | ROC, PR curve, confusion matrix, calibration, threshold tradeoff |
| `feature_importance.ipynb` | XGBoost importance, SHAP summary + dependence plots |
| `01_baseline_modeling.ipynb` | Initial baseline model (Decision Tree) |
| `02_aggregated_modeling.ipynb` | Aggregation-based feature validation |
| `03_full_feature_modeling.ipynb` | Full 24-feature XGBoost + CatBoost comparison |
| `04–07_eda_*.ipynb` | Exploratory data analysis per data source |
| `08_prepare_data.ipynb` | Feature engineering pipeline |

## Future Development

1. Migrate to managed K8s (EKS/GKE/AKS) for production-grade HA and auto-scaling
2. Add business rule engine alongside ML scoring
3. Authentication/authorization security layer
4. Production dashboards (Kibana, Grafana)
5. ClickHouse read replicas to separate read/write workloads
6. Optimize Kafka consumers (multi-threaded) and serving pod fan-out
7. OCR/text extraction from uploaded documents (payslips, IDs) for additional features

## Reference

- [Building async ML Inference Pipelines with Knative Eventing and KServe](https://medium.com/cars24-data-science-blog/building-asynchronous-ml-inference-pipelines-with-knative-eventing-and-kserve-79a7ab80bc79)

## Assumptions

- **Processing time target**: Within 1 day from application submission (many institutions take longer due to partial manual review — this system is 100% automated)

## License

This project is licensed under the MIT License — see [LICENSE](LICENSE) for details.
