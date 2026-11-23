"""Per-decision explanations (E14).

SHAP TreeExplainer on the booster inside the sklearn pipeline, mapped back to the
model's input columns, then turned into applicant-facing reason codes through the
feature catalog's reason map (shipped in the Bento as ``reason_map.json``).

The reason-code logic is pure and does not need ``shap``; only ``Explainer`` does.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Sequence

# XGBoost evaluates in float32, so attributions match the margin to about 1e-5.
ADDITIVITY_TOLERANCE = 1e-4


@dataclass(frozen=True)
class ReasonMap:
    """feature -> reason code, for explainable features only (protected, sensitive and proxies excluded)."""

    codes: Mapping[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path | str) -> "ReasonMap":
        path = Path(path)
        if not path.exists():
            return cls({})
        return cls(dict(json.loads(path.read_text(encoding="utf-8"))))


def reason_codes_from_contributions(
    contributions: Mapping[str, float], reason_map: ReasonMap, limit: int = 4
) -> list[str]:
    """Risk-raising contributions grouped by reason code, largest first.

    Features without a code (or excluded from reasons) never become reasons, even
    when their contribution is the largest.
    """
    totals: dict[str, float] = {}
    for feature, value in contributions.items():
        code = reason_map.codes.get(feature)
        if code is None or value <= 0:
            continue
        totals[code] = totals.get(code, 0.0) + float(value)
    return [code for code, _ in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]]


@dataclass(frozen=True)
class Explanation:
    base_value: float
    margin: float
    contributions: dict
    reason_codes: list
    additive_ok: bool

    def to_event_fields(self) -> dict:
        return {
            "contributions": {k: round(v, 6) for k, v in self.contributions.items()},
            "explanation": {
                "base_value": round(self.base_value, 6),
                "margin": round(self.margin, 6),
                "additive_ok": self.additive_ok,
            },
        }


def output_columns(preprocessor) -> list[str]:
    """Input column for each output column of a fitted ColumnTransformer (1:1 transforms only)."""
    names: list[str] = []
    for name, _, columns in preprocessor.transformers_:
        if name == "remainder":
            continue
        names.extend(columns)
    return names


class Explainer:
    def __init__(self, pipeline, reason_map: ReasonMap, limit: int = 4):
        import shap  # imported lazily: only the scoring image installs it

        self._pre = pipeline.named_steps["pre"]
        self._clf = pipeline.named_steps["clf"]
        self._columns = output_columns(self._pre)
        self._explainer = shap.TreeExplainer(self._clf, model_output="raw")
        self._reason_map = reason_map
        self._limit = limit

    def explain(self, row) -> Explanation:
        transformed = self._pre.transform(row)
        values = self._explainer.shap_values(transformed)
        values = values[1] if isinstance(values, list) else values  # binary classifiers may return [neg, pos]
        contributions = {col: float(v) for col, v in zip(self._columns, values[0])}
        import numpy as np

        base = float(np.ravel(self._explainer.expected_value)[-1])
        margin = float(self._clf.predict(transformed, output_margin=True)[0])
        additive_ok = abs(base + sum(contributions.values()) - margin) < ADDITIVITY_TOLERANCE
        codes = reason_codes_from_contributions(contributions, self._reason_map, self._limit) if additive_ok else []
        return Explanation(base, margin, contributions, codes, additive_ok)


def explain_safely(explainer: "Explainer | None", row) -> "Explanation | None":
    """Explanations must never block a decision: failures return None and are logged by the caller."""
    if explainer is None:
        return None
    try:
        return explainer.explain(row)
    except Exception:  # pragma: no cover - defensive
        return None


__all__: Sequence[str] = [
    "ADDITIVITY_TOLERANCE",
    "Explainer",
    "Explanation",
    "ReasonMap",
    "explain_safely",
    "output_columns",
    "reason_codes_from_contributions",
]
