"""Applicant-facing texts for reason codes, read from the feature catalog (E14)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

_REASONS = Path(__file__).resolve().parents[1] / "training" / "feature_catalog" / "reasons.yaml"
_FALLBACK = {
    "en": "Your application needs further review",
    "vi": "Hồ sơ của bạn cần được xem xét thêm",
}


@lru_cache(maxsize=1)
def _texts() -> dict:
    import yaml

    return yaml.safe_load(_REASONS.read_text(encoding="utf-8")) or {}


def reason_texts(codes: list[str], locale: str = "vi") -> list[dict]:
    """[{code, text}] in the given order; unknown codes get a generic text, never a raw code."""
    texts = _texts()
    return [{"code": c, "text": texts.get(c, {}).get(locale) or _FALLBACK.get(locale, _FALLBACK["en"])} for c in codes]
