# feature-store

Feast definitions and the stream materialiser. The materialiser reads the three feature topics, writes to the online store (Redis), and publishes `hc.feature_ready` once every group for an application has arrived.

- Code: `feast_repo/` (entities, feature views and services, `stream_processor.py`, `redis_coordination.lua`)
- Image: `feast_repo/Dockerfile`
- Deploy: `deploy/` (kustomization: Redis, ConfigMaps, registry volume, apply Job, materialiser, HPA)
- Uses: Kafka topics produced by `stream-features` and `loan-api`. The schemas in `feast_repo/feature_schema` are generated from the feature catalog
- Test: `pytest tests/unit/consumers/test_stream_processor.py tests/unit/training/test_catalog.py`
- Run in the cluster: `make k8s-feature-registry`
