"""Tests for model loading helpers."""

import pytest
from unittest.mock import MagicMock, patch, mock_open

from scoring.model_registry import _load_local_model, _load_mlflow_model, load_model


class TestLoadLocalModel:
    @patch("importlib.import_module")
    def test_joblib_extension(self, mock_import):
        mock_joblib = MagicMock()
        mock_joblib.load.return_value = "fake_model"
        mock_import.return_value = mock_joblib

        result = _load_local_model("/tmp/model.joblib")
        assert result == "fake_model"
        mock_joblib.load.assert_called_once_with("/tmp/model.joblib")

    @patch("importlib.import_module")
    def test_pkl_extension(self, mock_import):
        mock_joblib = MagicMock()
        mock_joblib.load.return_value = "pkl_model"
        mock_import.return_value = mock_joblib

        result = _load_local_model("/tmp/model.pkl")
        assert result == "pkl_model"

    def test_unsupported_extension(self):
        with pytest.raises(ValueError, match="Unsupported model file"):
            _load_local_model("/tmp/model.txt")

    @patch("importlib.import_module", side_effect=ModuleNotFoundError)
    def test_joblib_fallback_to_pickle(self, mock_import):
        import pickle

        fake_model = {"type": "model"}
        pickled = pickle.dumps(fake_model)

        with patch("builtins.open", mock_open(read_data=pickled)):
            result = _load_local_model("/tmp/model.pkl")
            assert result == fake_model


class TestLoadMlflowModel:
    @patch("importlib.import_module")
    def test_sklearn_flavor(self, mock_import):
        mock_mlflow = MagicMock()
        mock_mlflow.sklearn.load_model.return_value = "sklearn_model"
        mock_import.return_value = mock_mlflow

        result = _load_mlflow_model("models:/my_model/Production")
        assert result == "sklearn_model"

    @patch("importlib.import_module")
    def test_fallback_to_pyfunc(self, mock_import):
        mock_mlflow = MagicMock()
        mock_mlflow.sklearn.load_model.side_effect = Exception("no sklearn")
        mock_mlflow.xgboost.load_model.side_effect = Exception("no xgboost")
        mock_mlflow.pyfunc.load_model.return_value = "pyfunc_model"
        mock_import.return_value = mock_mlflow

        result = _load_mlflow_model("models:/my_model/1")
        assert result == "pyfunc_model"


class TestLoadModel:
    def test_mlflow_missing_uri(self):
        with pytest.raises(ValueError, match="mlflow_model_uri is required"):
            load_model(source="mlflow", path=None, mlflow_uri=None)

    @patch("scoring.model_registry._load_local_model")
    @patch("os.path.exists", return_value=False)
    def test_local_returns_4_tuple(self, mock_exists, mock_load):
        mock_load.return_value = "local_model"
        model, name, version, feast_meta = load_model(
            source="local", path="/tmp/model.joblib", mlflow_uri=None
        )
        assert model == "local_model"
        assert name == "model.joblib"
        assert version is None
        assert feast_meta is None

    def test_no_path_no_mlflow_raises(self):
        with pytest.raises(ValueError, match="Provide model_path"):
            load_model(source="local", path=None, mlflow_uri=None)
