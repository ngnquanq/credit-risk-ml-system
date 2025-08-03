from sklearn.model_selection import StratifiedKFold
from lightgbm import LGBMClassifier
from sklearn.metrics import roc_auc_score, precision_recall_fscore_support
import numpy as np
from utils.validation import *

def cross_validate_model(model, X_train, y_train, n_splits=5, return_per_fold=False, verbose=False):
    """
    Perform stratified k-fold cross-validation and return mean metrics.
    Optionally return per-fold metrics.
    """
    if model=='lightgbm':
        model = LGBMClassifier(n_estimators=300, 
                                  is_unbalance=True,
                                  boosting_type='gbdt',
                                  objective='binary',
                                  class_weight='balanced',
                                  random_state=42,
                                  reg_alpha=0.1,  # Regularization term
                                  reg_lambda=0.1)  # Regularization term

    else:
        pass

    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
    
    metric_dict = {
        "gini": [],
        "brier": [],
        "ece": [],
        "auc": [],
        "recall": [],
        "precision": [],
    }

    per_fold_results = []

    for fold_idx, (train_index, test_index) in enumerate(skf.split(X_train, y_train), start=1):
        X_fold_train, X_fold_test = X_train[train_index], X_train[test_index]
        y_fold_train, y_fold_test = y_train[train_index], y_train[test_index]

        model.fit(X_fold_train, y_fold_train)
        y_pred = model.predict(X_fold_test)
        y_prob = model.predict_proba(X_fold_test)[:, 1]

        gini = calculate_gini_coef(y_fold_test, y_prob)
        brier = calculate_brier(y_fold_test, y_prob)
        ece = calculate_ece(y_fold_test, y_prob)
        auc = roc_auc_score(y_fold_test, y_prob)
        recall, precision, _ = precision_recall_fscore_support(y_fold_test, y_pred, average='binary')

        # Append to metric_dict
        metric_dict["gini"].append(gini)
        metric_dict["brier"].append(brier)
        metric_dict["ece"].append(ece)
        metric_dict["auc"].append(auc)
        metric_dict["recall"].append(recall)
        metric_dict["precision"].append(precision)

        # Per-fold tracking (optional)
        per_fold_results.append({
            "fold": fold_idx,
            "gini": gini,
            "brier": brier,
            "ece": ece,
            "auc": auc,
            "recall": recall,
            "precision": precision
        })

        if verbose:
            print(f"Fold {fold_idx}: Gini={gini:.4f}, AUC={auc:.4f}, Brier={brier:.4f}, ECE={ece:.4f}")

    # Aggregate average
    mean_metrics = {k: np.mean(v) for k, v in metric_dict.items()}

    if return_per_fold:
        return mean_metrics, per_fold_results
    else:
        return mean_metrics
