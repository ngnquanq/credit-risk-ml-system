"""Tests for scoring/service.py — core inference functions.

scoring/service.py has heavy module-level side effects (bentoml.Service(),
bentoml.importing() with bare imports like `from config import ...`).
We mock bentoml AND pre-register all bare-name modules so the import succeeds.
"""

import sys
import os
import pytest
from unittest.mock import MagicMock
import numpy as np


@pytest.fixture(scope="module", autouse=True)
def _mock_bentoml_and_import():
    """Mock bentoml + bare-name scoring modules, then import scoring.service."""
    # 1. Mock bentoml itself
    mock_bentoml = MagicMock()
    mock_bentoml.importing.return_value.__enter__ = MagicMock(return_value=None)
    mock_bentoml.importing.return_value.__exit__ = MagicMock(return_value=False)
    mock_bentoml.Service.return_value = MagicMock()
    mock_bentoml.exceptions = MagicMock()
    mock_bentoml.exceptions.BentoMLException = type("BentoMLException", (Exception,), {})

    saved_modules = {}
    modules_to_mock = ["bentoml", "bentoml.exceptions"]

    # 2. The bentoml.importing() block does bare imports:
    #    from config import settings
    #    from schemas import ScoreRequest, ...
    #    from pipeline import as_vector, postprocess
    #    from logger import configure_logger
    #    These resolve to application/scoring/{config,schemas,pipeline,logger}.py
    #    when PYTHONPATH=application, "config" resolves to core.config. We need
    #    the scoring-specific ones. Add scoring/ to sys.path temporarily.
    scoring_dir = os.path.join(os.path.dirname(__file__), "..", "..", "..", "application", "scoring")
    scoring_dir = os.path.abspath(scoring_dir)
    sys.path.insert(0, scoring_dir)

    for mod_name in modules_to_mock:
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mock_bentoml if mod_name == "bentoml" else getattr(mock_bentoml, mod_name.split(".")[-1])

    # Clear any cached scoring.service
    for key in list(sys.modules.keys()):
        if key == "scoring.service" or key.startswith("scoring.service."):
            saved_modules[key] = sys.modules.pop(key)

    import scoring.service as svc

    # 3. Populate globals that bentoml.importing() would set
    import pandas as pd
    from scoring.pipeline import as_vector as _as_vector, postprocess as _postprocess
    from scoring.schemas import ScoreRequest, ScoreResponse, ScoreByIdRequest
    from scoring.logger import configure_logger

    svc.pd = pd
    svc.as_vector = _as_vector
    svc.postprocess = _postprocess
    svc.ScoreRequest = ScoreRequest
    svc.ScoreResponse = ScoreResponse
    svc.ScoreByIdRequest = ScoreByIdRequest
    svc.configure_logger = configure_logger
    svc.logger = MagicMock()
    svc.app = MagicMock()
    svc.model = None
    svc.MODEL_NAME = "test_model"
    svc.MODEL_VERSION = "1"
    svc.MODEL_FEAST_METADATA = None
    svc._EXPECTED_COLUMNS = None

    yield svc

    # Restore
    sys.path.remove(scoring_dir)
    for mod_name, saved in saved_modules.items():
        if saved is not None:
            sys.modules[mod_name] = saved
        else:
            sys.modules.pop(mod_name, None)


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset mutable globals between tests."""
    import scoring.service as svc
    svc._EXPECTED_COLUMNS = None
    svc.MODEL_FEAST_METADATA = None
    svc.model = None
    svc.MODEL_NAME = "test_model"
    svc.MODEL_VERSION = "1"
    yield
    svc._EXPECTED_COLUMNS = None


# ---------------------------------------------------------------------------
# _map_feast_features
# ---------------------------------------------------------------------------

class TestMapFeastFeatures:
    def test_maps_with_feature_mapping(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {"feature_mapping": {"feat_a": "FEAT_A", "feat_b": "FEAT_B"}}
        result = svc._map_feast_features(
            {"view:feat_a": [1.5], "view:feat_b": [2.0]},
            ["view:feat_a", "view:feat_b"],
        )
        assert result == {"FEAT_A": 1.5, "FEAT_B": 2.0}

    def test_uppercase_fallback_without_mapping(self):
        import scoring.service as svc
        result = svc._map_feast_features({"view:income": [50000.0]}, ["view:income"])
        assert result == {"INCOME": 50000.0}

    def test_strips_view_prefix(self):
        import scoring.service as svc
        result = svc._map_feast_features(
            {"app:cnt_children": [3]}, ["app:cnt_children"]
        )
        assert "CNT_CHILDREN" in result

    def test_none_values_skipped(self):
        import scoring.service as svc
        result = svc._map_feast_features(
            {"v:a": [None], "v:b": [1.0]}, ["v:a", "v:b"]
        )
        assert "A" not in result
        assert "B" in result

    def test_missing_refs_skipped(self):
        import scoring.service as svc
        result = svc._map_feast_features({"v:a": [1.0]}, ["v:a", "v:missing"])
        assert len(result) == 1

    def test_string_values_kept_as_strings(self):
        import scoring.service as svc
        result = svc._map_feast_features({"v:gender": ["M"]}, ["v:gender"])
        assert isinstance(result["GENDER"], str)

    def test_numeric_values_cast_to_float(self):
        import scoring.service as svc
        result = svc._map_feast_features({"v:age": [35]}, ["v:age"])
        assert isinstance(result["AGE"], float)

    def test_empty_list_skipped(self):
        import scoring.service as svc
        result = svc._map_feast_features({"v:x": []}, ["v:x"])
        assert len(result) == 0


# ---------------------------------------------------------------------------
# _predict_proba_local
# ---------------------------------------------------------------------------

class TestPredictProbaLocal:
    def _call(self, mock_model):
        import scoring.service as svc
        svc.model = mock_model
        X = svc.pd.DataFrame([[1.0, 2.0]], columns=["a", "b"])
        return svc._predict_proba_local(X)

    def test_sklearn_predict_proba_binary(self):
        mock = MagicMock()
        mock.predict_proba.return_value = np.array([[0.3, 0.7]])
        result = self._call(mock)
        np.testing.assert_array_almost_equal(result, [0.7])

    def test_sklearn_single_column(self):
        mock = MagicMock()
        mock.predict_proba.return_value = np.array([[0.8]])
        result = self._call(mock)
        np.testing.assert_array_almost_equal(result, [[0.8]])

    def test_xgboost_sets_nthread(self):
        mock = MagicMock()
        mock.get_booster.return_value = True
        mock.predict_proba.return_value = np.array([[0.2, 0.8]])
        self._call(mock)
        mock.set_params.assert_called_once_with(nthread=1)

    def test_pyfunc_fallback(self):
        mock = MagicMock(spec=["predict"])
        mock.predict.return_value = np.array([0.6])
        result = self._call(mock)
        np.testing.assert_array_almost_equal(result, [0.6])

    def test_no_method_raises(self):
        mock = MagicMock(spec=[])
        with pytest.raises(RuntimeError, match="does not support prediction"):
            self._call(mock)


# ---------------------------------------------------------------------------
# _get_expected_columns
# ---------------------------------------------------------------------------

class TestGetExpectedColumns:
    def test_from_model_signature(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {"model_signature": {"inputs": ["A", "B"]}}
        assert svc._get_expected_columns() == ["A", "B"]

    def test_from_selected_features(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {"selected_features": ["a", "b"]}
        assert svc._get_expected_columns() == ["A", "B"]

    def test_signature_preferred(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {
            "model_signature": {"inputs": ["SIG"]},
            "selected_features": ["sel"],
        }
        assert svc._get_expected_columns() == ["SIG"]

    def test_missing_raises(self):
        import scoring.service as svc
        with pytest.raises(RuntimeError):
            svc._get_expected_columns()

    def test_empty_raises(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {}
        with pytest.raises(RuntimeError):
            svc._get_expected_columns()


# ---------------------------------------------------------------------------
# _extract_sk_id_curr_from_cdc
# ---------------------------------------------------------------------------

class TestServiceExtractCdc:
    def _call(self, msg):
        from scoring.service import _extract_sk_id_curr_from_cdc
        return _extract_sk_id_curr_from_cdc(msg)

    def test_plain(self):
        assert self._call({"sk_id_curr": "100"}) == "100"

    def test_debezium(self):
        assert self._call({"payload": {"after": {"sk_id_curr": "200"}}}) == "200"

    def test_before(self):
        assert self._call({"payload": {"before": {"sk_id_curr": "300"}}}) == "300"

    def test_value_nested(self):
        assert self._call({"value": {"sk_id_curr": "400"}}) == "400"

    def test_empty(self):
        assert self._call({}) is None

    def test_none(self):
        assert self._call(None) is None

    def test_int_to_str(self):
        assert self._call({"sk_id_curr": 12345}) == "12345"


# ---------------------------------------------------------------------------
# _as_dataframe_row
# ---------------------------------------------------------------------------

class TestAsDataframeRow:
    def test_single_row(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {"model_signature": {"inputs": ["A", "B"]}}
        df = svc._as_dataframe_row({"A": 1.0, "B": 2.0})
        assert list(df.columns) == ["A", "B"]
        assert len(df) == 1

    def test_missing_filled_none(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {"model_signature": {"inputs": ["A", "B"]}}
        df = svc._as_dataframe_row({"A": 1.0})
        assert df["B"].iloc[0] is None


# ---------------------------------------------------------------------------
# _predict_and_create_response
# ---------------------------------------------------------------------------

class TestPredictAndCreateResponse:
    def test_returns_expected_keys(self):
        import scoring.service as svc
        svc.MODEL_FEAST_METADATA = {"model_signature": {"inputs": ["F"]}}
        svc.MODEL_NAME = "test"
        svc.MODEL_VERSION = "1"

        mock_model = MagicMock()
        mock_model.predict_proba.return_value = np.array([[0.3, 0.7]])
        svc.model = mock_model
        svc.settings = MagicMock(prediction_threshold=0.5)

        result = svc._predict_and_create_response({"F": 1.0}, "100")

        assert result["sk_id_curr"] == "100"
        assert result["probability"] == 0.7
        assert result["decision"] == "reject"
        assert result["model"] == "test"
        assert "ts" in result
