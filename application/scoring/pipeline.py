"""Small preprocessing/postprocessing helpers to keep service slim."""

from typing import Sequence, Mapping, Tuple, Optional
import numpy as np


def as_vector(
    features: Mapping[str, float], feature_order: Optional[Sequence[str]]
) -> np.ndarray:
    """Convert dict features into a 2D array in a stable order."""
    if feature_order:
        ordered = [features.get(k, 0.0) for k in feature_order]
    else:
        # Stable order by key to avoid nondeterminism if not provided
        ordered = [v for _, v in sorted(features.items())]
    return np.asarray([ordered], dtype=float)


def postprocess(prob: float, threshold: float) -> Tuple[float, str]:
    """Map probability to business decision using threshold."""
    decision = "reject" if prob >= threshold else "approve"
    return float(prob), decision
