"""Feature catalog checks (E2) and the gender-free feature set (E6)."""

import json
from pathlib import Path

import pytest

from training.feature_catalog.catalog import Catalog, load_set_status
from training.feature_preprocessing import load_feature_set

REPO = Path(__file__).resolve().parents[3]
FEAST_SCHEMAS = REPO / "application" / "feast_repo" / "feature_schema"
SETS = sorted(p.stem for p in (REPO / "application" / "training" / "feature_catalog" / "sets").glob("*.json"))


@pytest.fixture(scope="module")
def catalog():
    return Catalog.load()


@pytest.mark.parametrize("version", SETS)
def test_every_set_entry_is_defined(catalog, version):
    check = catalog.check_set(load_feature_set(version).columns, load_set_status(version))
    assert check.unresolved == ()


@pytest.mark.parametrize("version", SETS)
def test_only_legacy_sets_may_use_protected_attributes(catalog, version):
    check = catalog.check_set(load_feature_set(version).columns, load_set_status(version))
    assert check.ok, f"{version} uses protected attributes {check.protected_used}"


def test_legacy_set_is_flagged_for_gender(catalog):
    check = catalog.check_set(load_feature_set("legacy-v1").columns, "legacy")
    assert check.protected_used == ("CODE_GENDER",)
    assert not catalog.check_set(load_feature_set("legacy-v1").columns, "candidate").ok


def test_gender_free_set_is_legacy_without_gender_in_the_same_order():
    legacy = load_feature_set("legacy-v1")
    v2 = load_feature_set("v2-no-gender")
    assert v2.entries == tuple(e for e in legacy.entries if e[0] != "CODE_GENDER")
    assert v2.digest != legacy.digest


def test_gender_free_set_is_fully_served(catalog):
    assert catalog.missing_from_serving(load_feature_set("v2-no-gender").columns, FEAST_SCHEMAS) == []


def test_serving_check_reports_the_gender_gap_in_the_legacy_set(catalog):
    # F-07: the Flink sink drops code_gender, so no Feast view serves it.
    assert catalog.missing_from_serving(load_feature_set("legacy-v1").columns, FEAST_SCHEMAS) == ["CODE_GENDER"]


def test_reasons_never_come_from_protected_sensitive_or_proxy_features(catalog):
    assert catalog.reason_code("CODE_GENDER") is None
    assert catalog.reason_code("NAME_INCOME_TYPE") is None  # proxy for gender
    assert catalog.reason_code("DAYS_BIRTH") is None  # sensitive
    assert catalog.reason_code("EXT_SOURCE_2") == "EXT_SCORE_LOW"


def test_every_reason_code_has_english_and_vietnamese_text(catalog):
    codes = {catalog.reason_code(c) for c in load_feature_set("v2-no-gender").columns} - {None}
    assert codes
    for code in codes:
        assert catalog.reason_text(code, "en")
        assert catalog.reason_text(code, "vi")


def _write_catalog(tmp_path, application, reasons=None):
    (tmp_path / "definitions").mkdir()
    (tmp_path / "definitions" / "application.yaml").write_text(json.dumps(application))
    (tmp_path / "definitions" / "external.yaml").write_text("[]")
    (tmp_path / "definitions" / "dwh.yaml").write_text("[]")
    (tmp_path / "reasons.yaml").write_text(json.dumps(reasons or {}))
    return tmp_path


def _definition(**overrides):
    base = {"name": "A", "dtype": "float", "producer": "p", "feast_field": "a", "description": "d"}
    return {**base, **overrides}


def test_duplicate_definitions_are_rejected(tmp_path):
    root = _write_catalog(tmp_path, [_definition(), _definition()])
    with pytest.raises(ValueError, match="more than once"):
        Catalog.load(root)


def test_unknown_sensitivity_is_rejected(tmp_path):
    root = _write_catalog(tmp_path, [_definition(sensitivity="secret")])
    with pytest.raises(ValueError, match="sensitivity"):
        Catalog.load(root)


def test_reason_code_without_text_is_rejected(tmp_path):
    root = _write_catalog(tmp_path, [_definition(reason_code="NEW_CODE")])
    with pytest.raises(ValueError, match="without texts"):
        Catalog.load(root)


def test_unresolved_set_entry_fails_the_check(tmp_path):
    catalog = Catalog.load(_write_catalog(tmp_path, [_definition()]))
    check = catalog.check_set(["A", "B"], "candidate")
    assert check.unresolved == ("B",)
    assert not check.ok
