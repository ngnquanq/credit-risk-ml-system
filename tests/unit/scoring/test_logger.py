"""Tests for scoring/logger.py — configure_logger."""

from scoring.logger import configure_logger


class TestConfigureLogger:
    def test_json_format(self):
        log = configure_logger(level="INFO", fmt="json")
        assert log is not None

    def test_text_format(self):
        log = configure_logger(level="DEBUG", fmt="text")
        assert log is not None

    def test_returns_logger(self):
        log = configure_logger()
        assert hasattr(log, "info")
        assert hasattr(log, "error")
