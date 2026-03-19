# Model Card — Credit Risk Default Prediction

## Model Details

| Field | Value |
|-------|-------|
| **Model type** | Binary classification (default vs. non-default) |
| **Framework** | XGBoost (`XGBClassifier`) via scikit-learn Pipeline |
| **Version** | Trained and registered via `application/training/train_register.py` |
| **Decision threshold** | 0.3 (tuned for high recall of defaults) |

### Hyperparameters

| Parameter | Value |
|-----------|-------|
| `n_estimators` | 300 |
| `max_depth` | 4 |
| `learning_rate` | 0.05 |
| `subsample` | 0.8 |
| `colsample_bytree` | 0.8 |
| `eval_metric` | logloss |

## Training Data

- **Source**: Home Credit Default Risk dataset (Kaggle)
- **Size**: 307,511 loan applications
- **Target**: `TARGET` — 1 = default, 0 = repaid
- **Class distribution**: 8.1% default (24,825) / 91.9% repaid (282,686)
- **Split**: 80/20 stratified train/test
- **Feature count**: 24 (19 numeric + 5 categorical)

### Feature Sources

| Source | Features | Examples |
|--------|----------|---------|
| Application baseline | 8 | EXT_SOURCE_1/2/3, DAYS_BIRTH, AMT_CREDIT |
| Bureau aggregations | 3 | BUREAU_DEBT_TO_CREDIT_RATIO, BUREAU_ACTIVE_CREDIT_SUM |
| POS cash balance | 3 | POS_MEAN_CONTRACT_LENGTH, POS_TOTAL_MONTHS_OBSERVED |
| Previous applications | 3 | PREV_ANNUITY_MEAN, PREV_REFUSAL_RATE |
| Demographics | 2 | CNT_CHILDREN, DAYS_EMPLOYED |
| Categorical | 5 | CODE_GENDER, NAME_EDUCATION_TYPE, ORGANIZATION_TYPE |

### Feature Engineering

- **Quantile clipping**: 0.1st–99.9th percentiles to cap outliers
- **Imputation**: Median for numeric, zero-fill for PREV_* counts, mode for categorical
- **Encoding**: OrdinalEncoder for categorical features (handle_unknown → -1)

## Performance

| Metric | Value |
|--------|-------|
| **AUC (ROC)** | ~0.77 |
| **Accuracy @ threshold 0.3** | ~0.77 |

See `notebook/model_evaluation.ipynb` for full evaluation: ROC curve, precision-recall curve, confusion matrix, calibration plot, and threshold tradeoff analysis.

See `notebook/feature_importance.ipynb` for SHAP analysis and feature importance breakdown.

## Intended Use

- **Primary use**: Automated credit risk screening for personal loan applications
- **Users**: Lending operations team, credit risk analysts
- **Deployment**: Real-time inference via KServe + BentoML, consuming Kafka events
- **Decision flow**: Application → CDC → Feature enrichment (Feast) → Model scoring → Approve/Reject

## Limitations

- **Dataset vintage**: Based on historical Home Credit data; distributions may shift over time
- **Feature availability**: Requires external bureau scores (EXT_SOURCE_*) which are the strongest predictors — model degrades significantly without them
- **Threshold sensitivity**: The 0.3 threshold prioritizes default recall over approval volume; different business contexts may require recalibration
- **No reject inference**: Model trained only on approved applicants — selection bias may underestimate risk for profiles that were previously rejected

## Fairness & Bias Considerations

- `CODE_GENDER` is included as a feature. In many jurisdictions, using gender in credit decisions is prohibited. Before production deployment, evaluate whether removing this feature is required for regulatory compliance.
- The model has not been formally audited for disparate impact across protected classes. A fairness assessment (equal opportunity, demographic parity) should be conducted before production use.
- Ordinal encoding of categorical features (education, family status, income type) imposes an arbitrary ordering that may amplify or mask biases.

## Monitoring

- Track AUC and default rate on live predictions via MLflow + Grafana
- Compare predicted probability distributions against training baseline (PSI / KS drift detection)
- Retrain when AUC degrades below 0.72 or population stability index exceeds 0.2
