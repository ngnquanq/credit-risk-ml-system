"""Reason codes from contributions (E14). The SHAP explainer itself needs the scoring image."""

import json

import pytest

from scoring.explain import Explanation, ReasonMap, reason_codes_from_contributions
from training.feature_catalog.catalog import Catalog
from training.feature_catalog.export import reason_map

MAP = ReasonMap({
    "EXT_SOURCE_1": "EXT_SCORE_LOW",
    "EXT_SOURCE_2": "EXT_SCORE_LOW",
    "AMT_CREDIT": "CREDIT_AMOUNT_HIGH",
    "DAYS_EMPLOYED": "EMPLOYMENT_LENGTH_SHORT",
    "PREV_REFUSAL_RATE": "PREVIOUS_REFUSALS",
    "AMT_INCOME_TOTAL": "INCOME_LOW",
})


def test_contributions_are_grouped_by_code_and_ordered():
    contributions = {"EXT_SOURCE_1": 0.2, "EXT_SOURCE_2": 0.3, "AMT_CREDIT": 0.4, "DAYS_EMPLOYED": 0.1}
    assert reason_codes_from_contributions(contributions, MAP) == [
        "EXT_SCORE_LOW", "CREDIT_AMOUNT_HIGH", "EMPLOYMENT_LENGTH_SHORT"
    ]


def test_only_risk_raising_contributions_become_reasons():
    assert reason_codes_from_contributions({"AMT_CREDIT": -0.5, "DAYS_EMPLOYED": 0.01}, MAP) == ["EMPLOYMENT_LENGTH_SHORT"]


def test_unmapped_features_never_become_reasons_even_when_largest():
    contributions = {"NAME_INCOME_TYPE": 2.0, "DAYS_BIRTH": 1.5, "AMT_CREDIT": 0.1}
    assert reason_codes_from_contributions(contributions, MAP) == ["CREDIT_AMOUNT_HIGH"]


def test_at_most_four_reasons():
    contributions = {f: 1.0 + i for i, f in enumerate(MAP.codes)}
    assert len(reason_codes_from_contributions(contributions, MAP)) == 4


def test_generated_reason_map_excludes_protected_sensitive_and_proxy_features():
    generated = reason_map(Catalog.load())
    for feature in ("CODE_GENDER", "NAME_INCOME_TYPE", "DAYS_BIRTH", "NAME_FAMILY_STATUS", "CNT_CHILDREN"):
        assert feature not in generated
    assert generated["EXT_SOURCE_2"] == "EXT_SCORE_LOW"


def test_reason_map_loads_from_json(tmp_path):
    path = tmp_path / "reason_map.json"
    path.write_text(json.dumps({"AMT_CREDIT": "CREDIT_AMOUNT_HIGH"}))
    assert ReasonMap.load(path).codes == {"AMT_CREDIT": "CREDIT_AMOUNT_HIGH"}
    assert ReasonMap.load(tmp_path / "missing.json").codes == {}


def test_event_fields_are_rounded():
    fields = Explanation(-2.41, -0.8, {"AMT_CREDIT": 0.123456789}, ["CREDIT_AMOUNT_HIGH"], True).to_event_fields()
    assert fields["contributions"] == {"AMT_CREDIT": 0.123457}
    assert fields["explanation"] == {"base_value": -2.41, "margin": -0.8, "additive_ok": True}


def test_shap_additivity_on_a_real_booster():
    pytest.importorskip("shap")
    pytest.skip("Needs shap and an XGBoost runtime; run in the scoring image (E14 AC1).")
