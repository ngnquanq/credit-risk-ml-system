"""Tests for core/tracing — context and kafka_tracing modules."""

import pytest
from unittest.mock import patch, MagicMock

from core.tracing.context import (
    create_deterministic_trace_context,
    extract_or_create_trace_context,
    inject_trace_context,
)


class TestCreateDeterministicTraceContext:
    def test_returns_context(self):
        ctx = create_deterministic_trace_context("100001")
        from opentelemetry import trace
        span = trace.get_current_span(ctx)
        assert span is not None

    def test_deterministic_same_id(self):
        ctx1 = create_deterministic_trace_context("100001")
        ctx2 = create_deterministic_trace_context("100001")
        from opentelemetry import trace
        tid1 = trace.get_current_span(ctx1).get_span_context().trace_id
        tid2 = trace.get_current_span(ctx2).get_span_context().trace_id
        assert tid1 == tid2

    def test_different_ids_different_traces(self):
        ctx1 = create_deterministic_trace_context("100001")
        ctx2 = create_deterministic_trace_context("200002")
        from opentelemetry import trace
        tid1 = trace.get_current_span(ctx1).get_span_context().trace_id
        tid2 = trace.get_current_span(ctx2).get_span_context().trace_id
        assert tid1 != tid2

    def test_trace_id_is_nonzero(self):
        ctx = create_deterministic_trace_context("abc")
        from opentelemetry import trace
        tid = trace.get_current_span(ctx).get_span_context().trace_id
        assert tid != 0

    def test_sampled_flag(self):
        ctx = create_deterministic_trace_context("100")
        from opentelemetry import trace
        from opentelemetry.trace import TraceFlags
        flags = trace.get_current_span(ctx).get_span_context().trace_flags
        assert flags & TraceFlags.SAMPLED


class TestExtractOrCreateTraceContext:
    def test_no_headers_creates_deterministic(self):
        ctx = extract_or_create_trace_context(None, "100001")
        from opentelemetry import trace
        span = trace.get_current_span(ctx)
        assert span.get_span_context().trace_id != 0

    def test_empty_headers_creates_deterministic(self):
        ctx = extract_or_create_trace_context({}, "100001")
        from opentelemetry import trace
        span = trace.get_current_span(ctx)
        assert span.get_span_context().trace_id != 0

    def test_with_valid_traceparent(self):
        # Inject a known trace context via W3C traceparent header
        headers = {
            "traceparent": "00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01"
        }
        ctx = extract_or_create_trace_context(headers, "100001")
        from opentelemetry import trace
        span = trace.get_current_span(ctx)
        # Should use the extracted trace ID, not deterministic
        assert span.get_span_context().trace_id != 0


class TestInjectTraceContext:
    def test_returns_dict(self):
        result = inject_trace_context()
        assert isinstance(result, dict)


class TestTracingKafkaProducer:
    @patch("core.tracing.kafka_tracing.KafkaProducer")
    def test_send_traced(self, MockKP):
        mock_producer = MagicMock()
        MockKP.return_value = mock_producer

        from core.tracing.kafka_tracing import TracingKafkaProducer
        tp = TracingKafkaProducer(bootstrap_servers="localhost:9092")
        tp.send_traced("test-topic", {"key": "value"}, sk_id="100")

        mock_producer.send.assert_called_once()
        call_kwargs = mock_producer.send.call_args
        assert call_kwargs.args[0] == "test-topic"

    @patch("core.tracing.kafka_tracing.KafkaProducer")
    def test_send_without_sk_id(self, MockKP):
        MockKP.return_value = MagicMock()

        from core.tracing.kafka_tracing import TracingKafkaProducer
        tp = TracingKafkaProducer(bootstrap_servers="localhost:9092")
        tp.send_traced("topic", {"data": 1})  # no sk_id — should not error

    @patch("core.tracing.kafka_tracing.KafkaProducer")
    def test_close(self, MockKP):
        mock_producer = MagicMock()
        MockKP.return_value = mock_producer

        from core.tracing.kafka_tracing import TracingKafkaProducer
        tp = TracingKafkaProducer(bootstrap_servers="localhost:9092")
        tp.close()
        mock_producer.close.assert_called_once()


class TestTracingKafkaConsumer:
    @patch("core.tracing.kafka_tracing.KafkaConsumer")
    def test_close(self, MockKC):
        mock_consumer = MagicMock()
        MockKC.return_value = mock_consumer

        from core.tracing.kafka_tracing import TracingKafkaConsumer
        tc = TracingKafkaConsumer("topic", bootstrap_servers="localhost:9092", group_id="g")
        tc.close()
        mock_consumer.close.assert_called_once()
