# Training Module Refactor Implementation Plan

**Goal** Give training callers one source of truth for feature selection, preprocessing and calibration measurement.

**Architecture** Start at the in-process seam shared by CLI training and notebook experiments. Preserve ordered inputs, fitted transforms and existing artifact class locations. Extend the seam to Kubeflow after comparing its data and artifact contracts.

**Tech stack** Python, pandas, NumPy, scikit-learn, Kubeflow, MLflow.

**Spec** [Feature parity](../../03-handoff/E2-feature-catalog-and-parity.md) and [governed model](../../03-handoff/E6-fair-governed-model.md).

## 1. Share local training preprocessing

- [x] Extract the ordered legacy feature lists, preprocessing factory and ECE into `application/training/feature_preprocessing.py`.
- [x] Use the factory from `application/training/train_register.py` and `notebook/model_pipeline.py`. Preserve script commands. Pass each caller's existing clipping transformer so model class resolution stays compatible.
- [x] Derive notebook plot labels from fitted preprocessing columns.
- [x] Verify fresh fits, column order, nulls, unknown categories, ECE endpoints and both CLI help commands. Keep the current feature set and metric semantics in this refactor.

## 2. Reconcile Kubeflow inputs and execution packaging

- [x] Inventory Kubeflow differences in `platform/ml/k8s/training-pipeline/pipeline.py`. Ray tuning and registration take every column except `TARGET`, so entity IDs enter the model when present. Both infer categories from pandas dtype and use median imputation across numeric columns. The local recipe uses an ordered allowlist, quantile clipping and separate previous-loan imputation. Kubeflow emits lowercase feature metadata and logs bootstrap intervals.
- [x] Package the recipe for both Kubeflow tuning and registration and recompile `training_pipeline.yaml`. Verify both compiled task bodies select inputs and build preprocessing through the shared module.
- [ ] Run the same fixture through CLI and Kubeflow. Compare signatures, held-out predictions and metadata, then load an artifact through the scoring path. Establish a working Kubeflow run before switching registration.

## 3. Extend the feature contract to online consumers

- [ ] Define and version the feature catalog in E2. Generate or check Feast, Flink and model metadata schemas against the same ordered contract.
- [ ] Validate the existing serving schema against the catalog. Run the 50-applicant parity check before deploying transform corrections. Preserve the previous schema and model as a compatible rollback pair.
- [ ] Apply E6's protected-feature exclusion in a separately evaluated candidate. Record discrimination, fairness and serving parity before promotion.
