"""Tests for KafkaScoringGateway (fire-and-forget semantics)."""

import json
import pytest
from unittest.mock import patch, MagicMock

from infrastructure.external.kafka_scoring import KafkaScoringGateway


@pytest.fixture
def gateway():
    with patch("infrastructure.external.kafka_scoring.Producer") as MockProducer:
        mock_producer = MagicMock()
        MockProducer.return_value = mock_producer
        gw = KafkaScoringGateway()
        gw._mock_producer = mock_producer
        yield gw


class TestKafkaScoringGateway:
    async def test_produce_called_with_correct_args(self, gateway):
        await gateway.publish_for_scoring("APP001")

        gateway._mock_producer.produce.assert_called_once()
        call_kwargs = gateway._mock_producer.produce.call_args
        assert call_kwargs.kwargs["key"] == b"APP001"
        payload = json.loads(call_kwargs.kwargs["value"])
        assert payload["sk_id_curr"] == "APP001"
        assert payload["type"] == "APPLICATION_SUBMITTED"

    async def test_poll_called_after_produce(self, gateway):
        await gateway.publish_for_scoring("APP001")

        gateway._mock_producer.poll.assert_called_once_with(0)

    async def test_produce_exception_swallowed(self, gateway):
        """Fire-and-forget: produce errors are logged, not raised."""
        gateway._mock_producer.produce.side_effect = Exception("Kafka down")

        # Should NOT raise
        await gateway.publish_for_scoring("APP001")

    async def test_buffer_error_swallowed(self, gateway):
        gateway._mock_producer.produce.side_effect = BufferError("Queue full")

        # Should NOT raise
        await gateway.publish_for_scoring("APP001")

    async def test_topic_from_settings(self, gateway):
        await gateway.publish_for_scoring("APP001")
        call_args = gateway._mock_producer.produce.call_args
        # topic may be passed as positional arg or keyword
        topic = call_args.args[0] if call_args.args else call_args.kwargs.get("topic")
        assert topic == gateway.topic
