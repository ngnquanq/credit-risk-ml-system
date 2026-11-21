"""Compare FLAML and logistic regression on synthetic credit-risk data."""

import json
from importlib.metadata import version

import numpy as np
import pandas as pd
from flaml import AutoML
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score


def main() -> None:
    rng = np.random.default_rng(42)
    n = 2400
    features = pd.DataFrame({
        "debt_ratio": rng.beta(2, 5, n),
        "prior_delinquencies": rng.poisson(0.55, n),
        "income": rng.lognormal(11, 0.5, n),
    })
    period = np.arange(n) / n
    log_odds = (
        -3.8 + 3 * features.debt_ratio + 0.7 * features.prior_delinquencies
        - 0.7 * np.log(features.income / 60_000) + 0.7 * period
    )
    target = rng.binomial(1, 1 / (1 + np.exp(-log_odds)))
    train, validation, test = slice(0, 1440), slice(1440, 1920), slice(1920, None)

    baseline = LogisticRegression(max_iter=1000)
    # Rescale income to a fixed unit. Both models see the rescaled column; tree learners are
    # unaffected by the scale, the linear baseline converges better.
    features["income"] /= 60_000
    baseline.fit(features.iloc[train], target[train])

    automl = AutoML()
    automl.fit(
        X_train=features.iloc[train], y_train=target[train],
        X_val=features.iloc[validation], y_val=target[validation],
        task="classification", metric="roc_auc", eval_method="holdout",
        estimator_list=["lgbm", "rf", "extra_tree"],
        time_budget=8, max_iter=24, n_jobs=1, seed=42,
        retrain_full=False, mlflow_logging=False, verbose=0,
    )

    results = {}
    for name, model in [("logistic_regression", baseline), ("flaml", automl)]:
        pd_estimate = model.predict_proba(features.iloc[test])[:, 1]
        results[name] = {
            "roc_auc": float(roc_auc_score(target[test], pd_estimate)),
            "average_precision": float(average_precision_score(target[test], pd_estimate)),
            "brier": float(brier_score_loss(target[test], pd_estimate)),
        }
    print(json.dumps({
        "flaml_version": version("flaml"),
        "best_estimator": automl.best_estimator,
        "split_sizes": [1440, 480, 480],
        "test_default_rate": float(target[test].mean()),
        "test_metrics": results,
    }, indent=2))


if __name__ == "__main__":
    main()
