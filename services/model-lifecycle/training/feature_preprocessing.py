"""Feature selection, preprocessing and calibration shared by training entry points."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re

import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OrdinalEncoder


_GROUPS = ("num_other", "num_prev_ratio", "num_prev_other", "cat")


@dataclass(frozen=True)
class FeatureSet:
    version: str
    entries: tuple[tuple[str, str], ...]
    digest: str

    @property
    def columns(self) -> list[str]:
        return [name for name, _ in self.entries]

    def group(self, name: str) -> list[str]:
        return [column for column, group in self.entries if group == name]

    def manifest(self) -> dict:
        return {
            "version": self.version,
            "features": [
                {"name": name, "preprocessing_group": group}
                for name, group in self.entries
            ],
        }


def _sets_dir() -> Path:
    from feature_catalog import SETS_DIR

    return SETS_DIR


def load_feature_set(version: str | None = None) -> FeatureSet:
    """Resolve a versioned, ordered training contract from the packaged catalog."""
    if version is None:
        version = os.environ.get("CRQ_FEATURE_SET", "legacy-v1")
    if not isinstance(version, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", version):
        raise ValueError(f"Invalid feature set version: {version!r}")
    path = _sets_dir() / f"{version}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"Unknown feature set: {version}") from exc
    if not isinstance(data, dict) or data.get("version") != version:
        raise ValueError(f"Feature set version does not match {version}")
    features = data.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"Feature set {version} must contain at least one feature")
    entries = []
    seen = set()
    for feature in features:
        if not isinstance(feature, dict):
            raise ValueError(f"Invalid feature entry in {version}: {feature!r}")
        name, group = feature.get("name"), feature.get("preprocessing_group")
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[A-Z][A-Z0-9_]*", name)
            or name in {"TARGET", "SK_ID_CURR"}
            or name in seen
            or group not in _GROUPS
        ):
            raise ValueError(f"Invalid or duplicate feature entry in {version}: {feature!r}")
        seen.add(name)
        entries.append((name, group))
    canonical = {"version": version, "features": [
        {"name": name, "preprocessing_group": group} for name, group in entries
    ]}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode()).hexdigest()
    return FeatureSet(version, tuple(entries), digest)


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


def build_preprocessor(clip_quantiles: type = ClipQuantiles, *, feature_set: FeatureSet | None = None) -> ColumnTransformer:
    """
    Build a fresh preprocessor for the ordered training features.

    Call this function fresh for every CV fold and Optuna trial to prevent
    leakage — the ColumnTransformer must be refit on each training partition.
    """
    feature_set = feature_set if feature_set is not None else load_feature_set()
    other_num_cols = feature_set.group("num_other")
    prev_ratio_cols = feature_set.group("num_prev_ratio")
    prev_other_cols = feature_set.group("num_prev_other")
    categorical_cols = feature_set.group("cat")

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
    if categorical_cols:
        transformers.append((
            "cat",
            Pipeline([
                ("impute", SimpleImputer(strategy="most_frequent")),
                ("ord", OrdinalEncoder(handle_unknown="use_encoded_value", unknown_value=-1)),
            ]),
            categorical_cols,
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


def select_training_data(frame: pd.DataFrame, feature_set: FeatureSet | None = None) -> tuple[pd.DataFrame, pd.Series]:
    """Select ordered model inputs and the target, rejecting incomplete snapshots."""
    if "TARGET" not in frame:
        raise ValueError("TARGET column not found in data")
    columns = (feature_set if feature_set is not None else load_feature_set()).columns
    missing = [name for name in columns if name not in frame]
    if missing:
        raise ValueError(f"Missing expected feature columns: {missing}")
    return frame[columns], frame["TARGET"].astype(int)
