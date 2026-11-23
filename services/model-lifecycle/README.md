# model-lifecycle

Everything between a feature set and a model that serves traffic: train, register, promote, build a bundle, deploy it.

| Part | Folder | What it does |
|---|---|---|
| Training | `training/` | Preprocessing, training, registration to MLflow. `model_pipeline.py` tunes and picks a model; `train_register.py` registers it |
| KFP pipeline | `pipeline/` | The same training as a Kubeflow pipeline, with its image |
| MLflow watcher | `mlflow-watcher/` | Starts a bundle build when a version is promoted to Production |
| Bento builder | `bento-builder/` | Builds the scoring bundle from `services/scoring` and uploads it |
| Serving watcher | `serving-watcher/` | Deploys a new bundle as an InferenceService and repoints the Sequence |

- Uses: `contracts/feature_catalog` (feature sets). Does not import other services (`lint-imports`)
- Test: `pytest tests/unit/training`
- Run: `python services/model-lifecycle/training/model_pipeline.py`, then `python services/model-lifecycle/training/train_register.py --config best_model_config.json`
- In the cluster: `make k8s-kubeflow`, `make k8s-model-registry`, `make k8s-mlflow-watcher`, `make k8s-model-serving`
