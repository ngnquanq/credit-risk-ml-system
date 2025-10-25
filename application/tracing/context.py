"""
Trace context utilities for distributed tracing across services
"""

import hashlib
from typing import Optional, Dict
from opentelemetry import trace
from opentelemetry.trace import SpanContext, TraceFlags, Link
from opentelemetry.propagate import extract, inject
from opentelemetry.context import Context


def create_deterministic_trace_context(sk_id_curr: str) -> Context:
    """
    Create a deterministic trace context based on SK_ID_CURR.

    This ensures all services processing the same loan application
    use the same trace ID, even if Debezium CDC doesn't inject context.

    Args:
        sk_id_curr: Loan application ID (SK_ID_CURR)

    Returns:
        OpenTelemetry Context with deterministic trace ID
    """
    # Generate deterministic trace_id from SK_ID_CURR (128-bit)
    hash_bytes = hashlib.sha256(f"loan_application:{sk_id_curr}".encode()).digest()
    trace_id = int.from_bytes(hash_bytes[:16], byteorder='big')

    # Generate span_id (use first 8 bytes, different from trace_id)
    span_id = int.from_bytes(hash_bytes[16:24], byteorder='big')

    # Create SpanContext
    span_context = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=True,
        trace_flags=TraceFlags(0x01),  # Sampled
    )

    # Create and return Context
    return trace.set_span_in_context(trace.NonRecordingSpan(span_context))


def extract_or_create_trace_context(
    kafka_headers: Optional[Dict[str, str]],
    sk_id_curr: str
) -> Context:
    """
    Extract trace context from Kafka headers, or create deterministic one.

    This is the key function for unified distributed tracing:
    1. Try to extract existing trace context from Kafka headers
    2. If none exists (e.g., from Debezium CDC), create deterministic one
    3. All services use this → same SK_ID_CURR = same trace ID

    Args:
        kafka_headers: Kafka message headers dict
        sk_id_curr: Loan application ID

    Returns:
        OpenTelemetry Context for parent span
    """
    # Try to extract existing trace context
    if kafka_headers:
        parent_context = extract(kafka_headers)

        # Check if valid trace context exists
        span = trace.get_current_span(parent_context)
        if span and span.get_span_context().trace_id != 0:
            return parent_context

    # No existing context → create deterministic one
    return create_deterministic_trace_context(sk_id_curr)


def inject_trace_context() -> Dict[str, str]:
    """
    Inject current trace context into dict for Kafka headers.

    Returns:
        Dict of trace headers to attach to Kafka message
    """
    headers = {}
    inject(headers)
    return headers
