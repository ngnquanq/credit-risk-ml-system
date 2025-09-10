Feast Streaming Feature Store (Kafka → Redis)
============================================

This repo defines 3 StreamFeatureViews that ingest from Kafka topics and write to
the online store (Redis), keyed by `sk_id_curr`:

- `hc.application_features` (from Flink)
- `hc.application_ext` (from external/bureau query service)
- `hc.application_dwh` (from DWH/ClickHouse query service)

Files
- `feature_store.yaml` — Feast configuration
- `entities.py` — Entity definition (`sk_id_curr`)
- `feature_views.py` — 3 StreamFeatureViews with Kafka sources
- `repository.py` — apply utility to register definitions

Prereqs
- Redis running (e.g., `make up-redis`)
- Kafka topics exist (e.g., `make create-kafka-topics`)
- Feast installed: `pip install 'feast[redis,kafka]'`

Environment variables (single source of truth)
- `FEAST_REDIS_URL` (default: `redis://localhost:6379/0`)
- `FEAST_KAFKA_BROKERS` (default: `localhost:9092`)
- `FEAST_PROJECT` (default: `hc`)
- `FEAST_REGISTRY_PATH` (default: `data/registry.db`)

Usage
1) Start Redis: `make up-redis`
2) Ensure Kafka topics are flowing (Flink + query services running)
3) Apply repository (auto-generates feature_store.yaml from env):
   `cd application/feast && python repository.py`
4) Online retrieval (from your scoring service):
   `fs = FeatureStore(repo_path='application/feast')`
   `features = fs.get_online_features(
        features=[
            'application_features:cnt_children',
            'external_features:ext_source_1',
            'dwh_features:agg_prev_loans',
        ],
        entity_rows=[{'sk_id_curr': 'CUST_123'}],
    ).to_dict()`

Notes
- The Flink job emits `ts` in both sinks; external and dwh services emit `as_of`.
- Adjust `BOOTSTRAP`/brokers in `feature_views.py` if needed.
- For production, use environment variables to configure brokers and Redis.
