"""Tests for scoring/config.py — ScoringSettings."""

import pytest
import os
from unittest.mock import patch


class TestScoringSettings:
    def _make(self, **env_vars):
        """Create ScoringSettings with controlled env vars."""
        env = {
            "SCORING_MODEL_SOURCE": "local",
            "SCORING_MODEL_PATH": "/tmp/model.joblib",
            **env_vars,
        }
        with patch.dict(os.environ, env, clear=False):
            from scoring.config import ScoringSettings
            return ScoringSettings()

    def test_defaults(self):
        s = self._make()
        assert s.model_source == "local"
        assert s.prediction_threshold == 0.3
        assert s.feast_enabled is True

    def test_threshold_from_env(self):
        s = self._make(SCORING_PREDICTION_THRESHOLD="0.7")
        assert s.prediction_threshold == 0.7

    def test_model_source_mlflow(self):
        s = self._make(SCORING_MODEL_SOURCE="mlflow", SCORING_MLFLOW_MODEL_URI="models:/m/1")
        assert s.model_source == "mlflow"
        assert s.mlflow_model_uri == "models:/m/1"

    def test_kafka_disabled_by_default(self):
        s = self._make()
        assert s.enable_kafka is False

    def test_feast_repo_path_default_is_absolute(self):
        s = self._make()
        assert os.path.isabs(s.feast_repo_path)

    def test_log_defaults(self):
        s = self._make()
        assert s.log_level in ("INFO", "DEBUG", "WARNING")
        assert s.log_format in ("json", "text")

    def test_require_customer_data_default_true(self):
        s = self._make()
        assert s.require_customer_data is True
