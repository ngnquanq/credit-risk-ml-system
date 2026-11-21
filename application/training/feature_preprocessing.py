"""Feature selection, preprocessing and calibration shared by training entry points."""

from typing import List

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder


FEATURES: List[str] = [
    "EXT_SOURCE_3", "EXT_SOURCE_2", "EXT_SOURCE_1",
    "DAYS_BIRTH", "AMT_GOODS_PRICE", "AMT_CREDIT", "AMT_ANNUITY", "DAYS_EMPLOYED",
    "CODE_GENDER", "BUREAU_DEBT_TO_CREDIT_RATIO", "BUREAU_ACTIVE_CREDIT_SUM",
    "NAME_EDUCATION_TYPE", "POS_MEAN_CONTRACT_LENGTH", "PREV_ANNUITY_MEAN",
    "PREV_GOODS_TO_CREDIT_RATIO", "NAME_FAMILY_STATUS", "POS_LATEST_MONTH",
    "ORGANIZATION_TYPE", "BUREAU_AMT_MAX_OVERDUE_EVER", "POS_TOTAL_MONTHS_OBSERVED",
    "AMT_INCOME_TOTAL", "PREV_REFUSAL_RATE", "NAME_INCOME_TYPE", "CNT_CHILDREN",
]
CAT_COLS: List[str] = [
    "CODE_GENDER", "NAME_EDUCATION_TYPE", "NAME_FAMILY_STATUS",
    "ORGANIZATION_TYPE", "NAME_INCOME_TYPE",
]
NUM_COLS: List[str] = [c for c in FEATURES if c not in CAT_COLS]


class ClipQuantiles(BaseEstimator, TransformerMixin):
    """Clip numeric inputs to quantiles fitted on the training partition."""

    def __init__(self, qlow: float = 0.001, qhigh: float = 0.999):
        self.qlow = qlow
        self.qhigh = qhigh

    def fit(self, X, y=None):
        frame = pd.DataFrame(X)
        self.lower_ = frame.quantile(self.qlow, interpolation="nearest")
        self.upper_ = frame.quantile(self.qhigh, interpolation="nearest")
        return self

    def transform(self, X):
        return pd.DataFrame(X).clip(self.lower_, self.upper_, axis=1).values


def build_preprocessor(clip_quantiles: type = ClipQuantiles) -> ColumnTransformer:
    """
    Build a fresh preprocessor for the ordered training features.

    Call this function fresh for every CV fold and Optuna trial to prevent
    leakage — the ColumnTransformer must be refit on each training partition.
    """
    prev_ratio_cols = [
        c for c in NUM_COLS if c.startswith("PREV_") and ("RATIO" in c or "RATE" in c)
    ]
    prev_other_cols = [
        c for c in NUM_COLS if c.startswith("PREV_") and c not in prev_ratio_cols
    ]
    other_num_cols = [c for c in NUM_COLS if not c.startswith("PREV_")]

    transformers = []
    if other_num_cols:
        transformers.append((
            "num_other",
            Pipeline([("clip", clip_quantiles()), ("impute", SimpleImputer(strategy="median"))]),
            other_num_cols,
        ))
    if prev_ratio_cols:
        # PREV_* ratio/rate columns: median fill (missing = no previous loan at all)
        transformers.append((
            "num_prev_ratio",
            Pipeline([("clip", clip_quantiles()), ("impute", SimpleImputer(strategy="median"))]),
            prev_ratio_cols,
        ))
    if prev_other_cols:
        # PREV_* count/amount columns: zero fill (absence is a meaningful signal)
        transformers.append((
            "num_prev_other",
            Pipeline([
                ("clip", clip_quantiles()),
                ("impute", SimpleImputer(strategy="constant", fill_value=0)),
            ]),
            prev_other_cols,
        ))
    if CAT_COLS:
        transformers.append((
            "cat",
            Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("ord", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
            ]),
            CAT_COLS,
        ))
    return ColumnTransformer(transformers, remainder="drop")


def ece_score(y_true: np.ndarray, y_prob: np.ndarray, n_bins: int = 10) -> float:
    """
    Expected Calibration Error (ECE).

    Weighted mean absolute gap between predicted probability and observed positive
    rate across equal-width probability bins. Lower is better; 0 = perfect.
    """
    y_true = np.asarray(y_true)
    y_prob = np.asarray(y_prob)
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (y_prob >= lo) & (y_prob < hi)
        if mask.sum() == 0:
            continue
        ece += mask.mean() * abs(y_true[mask].mean() - y_prob[mask].mean())
    return float(ece)


def select_training_data(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Select ordered model inputs and the target, rejecting incomplete snapshots."""
    if "TARGET" not in frame:
        raise ValueError("TARGET column not found in data")
    missing = [name for name in FEATURES if name not in frame]
    if missing:
        raise ValueError(f"Missing expected feature columns: {missing}")
    return frame[FEATURES], frame["TARGET"].astype(int)
