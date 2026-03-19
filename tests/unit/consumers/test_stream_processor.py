"""Tests for FeastStreamProcessor."""

import pytest
from unittest.mock import patch, MagicMock, mock_open


def _build_processor():
    """Build FeastStreamProcessor with all infra mocked out."""
    with patch("feast_repo.stream_processor.FeatureStore") as MockFS, \
         patch("feast_repo.stream_processor.KafkaProducer") as MockKP, \
         patch("feast_repo.stream_processor.redis.Redis") as MockRedis, \
         patch("builtins.open", mock_open(read_data="-- lua script")):
        mock_fs = MagicMock()
        MockFS.return_value = mock_fs
        mock_producer = MagicMock()
        MockKP.return_value = mock_producer
        mock_redis = MagicMock()
        mock_redis.ping.return_value = True
        mock_redis.register_script.return_value = MagicMock()
        MockRedis.return_value = mock_redis

        from feast_repo.stream_processor import FeastStreamProcessor
        proc = FeastStreamProcessor(repo_path="/tmp/fake")
        proc._mock_fs = mock_fs
        proc._mock_producer = mock_producer
        proc._mock_redis = mock_redis
        return proc


class TestExtractSkIdCurrAndFeatures:
    @pytest.fixture(autouse=True)
    def processor(self):
        self.proc = _build_processor()

    def test_plain_message(self):
        sk, feats = self.proc.extract_sk_id_curr_and_features(
            {"sk_id_curr": "100", "feat_a": 1.0, "feat_b": 2.0}
        )
        assert sk == "100"
        assert feats == {"feat_a": 1.0, "feat_b": 2.0}

    def test_debezium_envelope(self):
        msg = {"payload": {"after": {"sk_id_curr": "200", "x": 5}}}
        sk, feats = self.proc.extract_sk_id_curr_and_features(msg)
        assert sk == "200"
        assert feats == {"x": 5}

    def test_no_sk_id_returns_none(self):
        sk, feats = self.proc.extract_sk_id_curr_and_features({"other": 1})
        assert sk is None
        assert feats == {}

    def test_sk_id_excluded_from_features(self):
        sk, feats = self.proc.extract_sk_id_curr_and_features({"sk_id_curr": "1", "a": 1})
        assert "sk_id_curr" not in feats


class TestQueueFeaturesForBatch:
    @pytest.fixture(autouse=True)
    def processor(self):
        self.proc = _build_processor()

    def test_queues_to_correct_buffer(self):
        self.proc.queue_features_for_batch("100", "application", {"a": 1})
        assert not self.proc.batch_buffers["application"].empty()
        assert self.proc.batch_buffers["external"].empty()

    def test_empty_features_not_queued(self):
        self.proc.queue_features_for_batch("100", "application", {})
        assert self.proc.batch_buffers["application"].empty()


class TestFlushBatchToRedis:
    @pytest.fixture(autouse=True)
    def processor(self):
        self.proc = _build_processor()

    @patch.object(type(_build_processor()), "_expected_fields_for_source", return_value=["feat_a"])
    def test_writes_batch_to_feast(self, mock_fields):
        batch = [{"sk_id_curr": "100", "features": {"feat_a": 1.0}}]
        self.proc.coordination_script = MagicMock(return_value=1)

        self.proc._flush_batch_to_redis(batch, "application")

        self.proc._mock_fs.write_to_online_store.assert_called_once()
        call_kwargs = self.proc._mock_fs.write_to_online_store.call_args
        assert call_kwargs.kwargs["feature_view_name"] == "application_features"

    @patch.object(type(_build_processor()), "_expected_fields_for_source", return_value=["feat_a"])
    def test_publishes_when_coordination_returns_3(self, mock_fields):
        batch = [{"sk_id_curr": "100", "features": {"feat_a": 1.0}}]
        self.proc.coordination_script = MagicMock(return_value=3)

        with patch.object(self.proc, "publish_feature_ready_event") as mock_pub:
            self.proc._flush_batch_to_redis(batch, "external")
            mock_pub.assert_called_once_with("100", "external")

    @patch.object(type(_build_processor()), "_expected_fields_for_source", return_value=["feat_a"])
    def test_feast_write_failure_does_not_crash(self, mock_fields):
        batch = [{"sk_id_curr": "100", "features": {"feat_a": 1.0}}]
        self.proc._mock_fs.write_to_online_store.side_effect = Exception("Redis full")

        # Should not raise
        self.proc._flush_batch_to_redis(batch, "application")


class TestPublishFeatureReadyEvent:
    @pytest.fixture(autouse=True)
    def processor(self):
        self.proc = _build_processor()

    def test_producer_failure_logged_not_raised(self):
        self.proc._mock_producer.send.side_effect = Exception("Kafka down")
        # Should not raise
        self.proc.publish_feature_ready_event("100", "application")
