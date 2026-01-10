"""
Simple OpenTelemetry tracing utilities
"""

from .setup import setup_tracing
from .kafka_tracing import TracingKafkaProducer, TracingKafkaConsumer
from .context import (
    create_deterministic_trace_context,
    extract_or_create_trace_context,
    inject_trace_context,
)

__all__ = [
    "setup_tracing",
    "TracingKafkaProducer",
    "TracingKafkaConsumer",
    "create_deterministic_trace_context",
    "extract_or_create_trace_context",
    "inject_trace_context",
]
