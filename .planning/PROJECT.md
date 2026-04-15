# Home Credit — ML Model Quality Initiative

## What This Is

An end-to-end credit risk decisioning platform that scores loan applications through a Kafka → Feast → KServe ML pipeline. This initiative upgrades the data science layer: replacing the current single-split, uncalibrated, untuned baseline with a rigorously evaluated, calibrated model — promoted to MLflow Production so the whole pipeline benefits.

## Core Value

A credit risk model whose probability outputs can be trusted: calibrated probabilities that reflect true default rates, metric estimates with confidence bands from k-fold CV, and a justified model choice backed by hyperparameter tuning.

## Requirements

### Validated

These capabilities already exist and are confirmed working:

- ✓ XGBoost baseline model trained on 307K applications (AUC ~0.77) — existing
- ✓ Feature pipeline: 24 features across EXT_SOURCE, bureau, POS, previous applications — existing
- ✓ MLflow model registry with Production/Staging stages — existing
- ✓ BentoML scoring service on KServe (/v1/score, /v1/score-by-id) — existing
- ✓ Feast feature store (Redis online, MinIO offline) — existing
- ✓ EDA notebooks (bureau, POS, credit card, previous apps) — existing
- ✓ Feature importance notebook with SHAP analysis — existing
- ✓ model_evaluation.ipynb with ROC, PR curves, calibration plot (unmeasured/unapplied) — existing
- ✓ 194 unit + integration tests with CI gates — existing
- ✓ Kafka → Flink → Feast → KServe end-to-end pipeline — existing

### Active

What we're building in this initiative:

- [ ] Cross-validation replaces single 80/20 split — k-fold CV with stratification on imbalanced target
- [ ] Metric confidence intervals — AUC, precision, recall reported with bands (mean ± std across folds)
- [ ] Hyperparameter tuning — uncomment and execute Bayesian optimization in 03_full_feature_modeling.ipynb
- [ ] Model comparison decision — CatBoost vs XGBoost justified with tuned configs; winner documented
- [ ] Calibration measurement — Brier score, ECE, and calibration curve added to model_evaluation.ipynb
- [ ] Calibration correction — Platt scaling or isotonic regression applied to winning model
- [ ] train_register.py synced — reflects final model choice, tuned hyperparameters, calibration step
- [ ] Polished notebooks — commented-out code removed, cells run top-to-bottom without errors
- [ ] Best model promoted to MLflow Production — replaces untuned baseline

### Out of Scope

- Confidence intervals in /v1/score API response — deferred; serving changes come after notebook work validates approach
- Drift monitoring / data quality alerts — separate initiative
- Fairness / disparate impact evaluation — separate initiative
- Feature engineering expansion beyond current 24 features — separate initiative
- New model architectures (LightGBM, neural nets) — scope creep; tune existing before replacing

## Context

**Current weaknesses (from codebase analysis):**
- `notebook/03_full_feature_modeling.ipynb`: Bayesian hyperparameter tuning is commented out; CatBoost (0.7827 AUC) outperforms deployed XGBoost (0.7812) but XGBoost is in production
- `notebook/model_evaluation.ipynb`: calibration plot exists but calibration correction is never applied; only single train/test split metrics reported
- `application/training/train_register.py`: hardcoded XGBoost params (300 trees, depth=4, lr=0.05), no CV, diverges from notebook findings
- Decision threshold hardcoded at 0.3 — chosen by inspecting PR curve but not formally optimized

**Data:** 307,511 applications, 8.1% default rate (11.4:1 imbalance). `data/complete_feature_dataset.csv` is the authoritative training set.

**MLflow:** Already integrated — model registered at `models:/credit_risk_model/Production`. Promotion via `train_register.py` is the deployment mechanism.

## Constraints

- **Data**: Training data at `data/complete_feature_dataset.csv` is static — no new data sources in this initiative
- **Stack**: Python 3.10+, XGBoost + CatBoost + scikit-learn ecosystem — no new frameworks
- **Notebook-first**: All ML changes start in notebooks; `train_register.py` is updated to match, not vice versa
- **No serving changes**: BentoML/KServe serving contract unchanged — out of scope for this initiative
- **Model registry**: MLflow is the deployment gate — final model must be registered and promoted via existing pipeline

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Notebooks are authoritative, not train_register.py | User confirmed: notebooks are the real ML pipeline | — Pending |
| Calibration approach (Platt vs isotonic) | Platt scaling is parametric and more stable on small test sets; isotonic is more flexible but risks overfitting | — Pending |
| CV strategy (k=5 or k=10) | 5-fold balances compute cost vs variance on 307K rows; 10-fold if compute allows | — Pending |
| Model selection: CatBoost vs XGBoost | CatBoost leads by 0.0015 AUC untuned — post-tuning gap will determine final choice | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-15 after initialization*
