"""Small postprocessing helpers to keep service slim."""

from typing import Tuple


def postprocess(prob: float, threshold: float) -> Tuple[float, str]:
    """Map probability to business decision using threshold."""
    decision = "reject" if prob >= threshold else "approve"
    return float(prob), decision
