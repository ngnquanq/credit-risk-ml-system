# 1. Overview

This is the C4 description of the Credit Risk Decisioning Platform **as it is built in this repository**: the Kubernetes (Minikube) path that the `Makefile` deploys. It was checked against the code on 2026-11-21 (commit `7605340`). Where the design and the code disagree, these documents follow the code and record the difference in [Findings](07-findings.md).

The model lives in [`workspace.dsl`](../workspace.dsl). Every diagram here is generated from it, so change the DSL rather than the pictures.

> The original Minikube views describe the baseline before the Streamlit retirement. For the current web entry points, see [the applicant and staff portals](../../../../portals/README.md).

## What the system does

1. A loan application is submitted through a Streamlit UI and stored in PostgreSQL by a FastAPI service.
2. Debezium turns the committed row into a change event on Kafka.
3. Three branches run in parallel and each produce one feature group:
   - **Applicant features.** A PyFlink job derives them from the application itself.
   - **Bureau features.** A Python service fetches the applicant's bureau history from ClickHouse, and a second PyFlink job aggregates it into about 60 `BUREAU_*` features.
   - **Internal-history features.** A Python service looks up the applicant's previous-loan, POS and credit-card aggregates in the dbt marts.
4. A Feast stream materialiser writes all three groups to Redis. A Redis Lua script records which groups have arrived, and when all three are present it emits `hc.feature_ready`.
5. Knative Eventing delivers that event through a Sequence to a KServe InferenceService running a BentoML scoring service. The service reads the features from Feast, runs an XGBoost pipeline and returns a decision, which a KafkaSink writes to `hc.scoring`.
6. Separately, models are trained (locally or with Kubeflow and Ray) and registered in MLflow. Promoting a version to `Production` builds a new Bento and image, creates a new InferenceService and re-points the Sequence at it, with no manual step.

## Scope

| In scope | Out of scope / superseded |
|---|---|
| Everything under `application/`, `platform/*/k8s/`, `ml_data_mart/`, the `Makefile` targets `k8s-*`, `tests/test_load/` | The Docker Compose stacks (Airflow, DataHub, Superset, Vault, Spark, Jenkins, nginx gateway). ADR-0005 moved the platform to Kubernetes, and the Compose files were deleted on 2026-11-21 (recoverable from git history). |
| Runtime, data, deployment and model-lifecycle views | Business rules engine, authentication, OCR (listed as future work in the README) |

## How to read the views

| Level | View key | Question it answers |
|---|---|---|
| L0 | `L0-Landscape` | What exists around the platform? |
| L1 | `L1-Context` | Who uses it, and which external systems does it depend on? |
| L2 | `L2-All` | Every container and how they connect (dense; use the per-plane views to read it) |
| L2 | `L2-1-Intake` | UI, API, operational database, documents, hand-off to CDC |
| L2 | `L2-2-Feature-Pipeline` | One CDC topic → three feature topics → online store → readiness event |
| L2 | `L2-3-Scoring` | Readiness event → Knative → KServe → decision topic, and what changes the predictor |
| L2 | `L2-4-Warehouse` | CSVs → ClickHouse → dbt marts → training snapshot |
| L2 | `L2-5-Model-Lifecycle` | Train → register → promote → build → deploy |
| L2 | `L2-6-Ops` | Observability and the load-test harness |
| L2 | `L2-7-Kafka-Topology` | Every producer and consumer of every topic |
| L3 | `L3-API`, `L3-Flink`, `L3-Bureau-Service`, `L3-DWH-Service`, `L3-Feast-Materialiser`, `L3-Scoring-Service`, `L3-Training-Pipeline`, `L3-dbt` | The internals of each custom-code container |
| Dynamic | `D1` … `D8` | Numbered runtime flows (see [Runtime sequences](04-runtime-sequences.md) for full sequence diagrams) |
| Deployment | `Deploy-Minikube-All`, `Deploy-Minikube-RealTime` | Namespaces, workloads, replica counts |

## Notation

| Shape / colour | Meaning |
|---|---|
| Person | A human role |
| Blue box | Container we run (custom code or configured product) |
| Light blue box | Component inside a custom-code container |
| Orange pipe | Kafka topic (modelled as a container so producers and consumers are explicit) |
| Green cylinder / folder | Database / object store |
| Purple hexagon | Knative Eventing resource |
| Grey robot | Controller that reconciles Kubernetes resources |
| Grey box | Batch Job or infrastructure product |
| **Red outline** (`Risk`) | Works, but has a defect or fragility recorded in [Findings](07-findings.md) |
| **Dashed red** (`Gap`) | Missing: the design implies it, but nothing implements it |
| Dashed / faded (`Optional`, `Unused`) | Deployed or wired but not active on the default path |

Relationships point in the direction of **dependency** (who initiates). A consumer points *to* the topic it reads from, and the arrow label says "Consumes". To follow data instead of dependencies, use the [Data flow](05-data-flow.md) section.

## Key numbers

| Item | Value | Source |
|---|---|---|
| Training data | 307,511 applications, 8.1% default | Kaggle Home Credit Default Risk |
| Model | XGBoost, 300 trees, depth 4, lr 0.05, 24 features (19 numeric, 5 categorical), threshold 0.3 | `application/training/train_register.py` |
| Test AUC | ~0.77 | README |
| Kafka | 1 broker, 8 platform topics × 4 partitions, RF 1 | `platform/data/k8s/message-broker/04-kafka-init.yaml` |
| Latest load test | 29.4 insert RPS for 3 min; only 17.5% of events reached `hc.scoring` in the window; bottleneck is KafkaChannel → KServe delivery | `tests/test_load/RESULTS.md` |
| Cluster | Minikube, 20 CPU, 24 GB RAM, 80 GB disk, 15 namespaces | `Makefile` (`k8s-up`) |
| Tests | 179 passed, 1 skipped (unit + integration), after removing tests for deleted dead code | local run, 2026-11-21 |

## Architecture decisions

Decisions are recorded as ADRs in [`docs/adr/`](../../../adr/): ClickHouse (0001), Kafka event-driven (0002), Feast (0003), KServe + BentoML (0004), Kubernetes (0005), Flink (0007), load-test fixes (0008), training and promotion pipeline (0009), Knative Sequence (0010). ADR-0006 (Clean Architecture) is referenced from `docs/architecture/system-overview.md` but the file does not exist.
