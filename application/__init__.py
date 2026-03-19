"""
Application package - Home Credit Credit Risk System
"""

# Export tracing utilities for easy import across all services
from .tracing import setup_tracing, TracingKafkaProducer, TracingKafkaConsumer

__all__ = [
    "setup_tracing",
    "TracingKafkaProducer",
    "TracingKafkaConsumer",
]
