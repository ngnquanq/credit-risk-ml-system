# scoring

Scores one application (BentoML service on KServe). Input: an application id. It reads the three feature groups from the online store, runs the model, applies the decision policy, and returns a band, a score and reason codes.

- Code: `service.py` (endpoints), `policy.py` (score to band), `explain.py` (reasons), `model_registry.py`, `config.py`
- Image: built by the bento builder (`services/model-lifecycle/bento-builder`) from `bentofile.yaml`; `APP_SUBPATH` is `services/scoring`
- Deploy: `deploy/` holds the Knative wiring (Sequence, KafkaSource, KafkaSinks). The KServe and Knative installs are in `platform/`
- Uses: `contracts/feature_catalog` (feature names, reason texts), the Feast repo registry from `services/feature-store`
- Does not import: any other service (`lint-imports`). One known exception is the optional `core.tracing` import in `service.py`
- Test: `pytest tests/unit/scoring`
- Run in the cluster: `make k8s-scoring-pipeline`, `make k8s-model-serving`
