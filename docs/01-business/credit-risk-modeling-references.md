# Credit risk modeling references

## Dataset and validation

- **Home Credit Default Risk (2018)** is the dataset linked in this repository's README. Its competition used ROC AUC. Use the supplied labels and one frozen split for model comparisons. Local AUC and private leaderboard AUC use different evaluation samples. [Official evaluation](https://www.kaggle.com/competitions/home-credit-default-risk/overview/prizes)
- **Home Credit Credit Risk Model Stability (2024)** is a separate challenge that evaluates discrimination and stability across weeks. It is a reference for designing out-of-time evaluation when the snapshot has a reliable decision date and sufficiently mature labels. [Official challenge](https://www.kaggle.com/competitions/home-credit-credit-risk-model-stability/overview/tracks-and-awards)

## Model development and review

- **Benchmarking credit scoring classifiers** (Lessmann et al.) compares 41 classifiers across eight datasets. For this project, compare a logistic-regression baseline, the existing boosted model, and an AutoML challenger on the same feature contract, splits and metrics. [Accepted manuscript](https://eprints.soton.ac.uk/377196/1/Lessmann_Benchmarking.pdf)
- **Calibration of probability-of-default models** (Fonseca and Lopes) studies Platt scaling and isotonic regression across credit scoring datasets. Report ROC AUC and average precision for ranking, and Brier score and a reliability plot for probability quality. Fit any calibrator before the final test. [Paper](https://arxiv.org/abs/1710.08901)
- **Reject inference in credit scoring** (Ehrhardt et al.) explains the limitations of learning and validating with outcomes observed only for financed applicants. Document who has an observed label and the population represented by the metrics. [Paper](https://pubmed.ncbi.nlm.nih.gov/35707081/)

## AutoML smoke test

[The FLAML experiment](../../notebook/automl_smoke.py) generates synthetic data, uses an ordered train/validation/test split of 1,440/480/480, and compares FLAML against logistic regression. FLAML selects an estimator on the middle split using ROC AUC. Both models are evaluated on the final split. [FLAML documentation](https://microsoft.github.io/FLAML/docs/Use-Cases/Task-Oriented-AutoML/)

Run from the repository root in a separate Python environment.

```bash
python -m venv /tmp/credit-risk-automl
/tmp/credit-risk-automl/bin/python -m pip install 'flaml[automl]==2.8.0'
/tmp/credit-risk-automl/bin/python notebook/automl_smoke.py
```

The local run selected LightGBM. The synthetic test set had 68 defaults out of 480 rows.

| Model | ROC AUC | Average precision | Brier loss |
|---|---:|---:|---:|
| Logistic regression | 0.6703 | 0.2468 | 0.1172 |
| FLAML-selected LightGBM | 0.6373 | 0.2237 | 0.1198 |

This experiment exercises the tuning and evaluation flow. Evaluating a real challenger requires a versioned snapshot, the repository's ordered feature contract, and comparable metrics for the incumbent on the same holdout. FLAML remains an optional research dependency.
