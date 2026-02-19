"""
Simple OpenTelemetry setup
"""

import os
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
from opentelemetry.sdk.resources import Resource
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter


def setup_tracing(service_name: str, sampling_rate: float = 0.1):
    """
    Initialize tracing for a service

    Args:
        service_name: Name of this service (e.g., "api-service")
        sampling_rate: Fraction to sample (0.1 = 10%)

    Returns:
        Tracer instance
    """
    # Get Jaeger endpoint from env or use default
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:30317")

    # Create resource with service name
    resource = Resource(attributes={
        "service.name": service_name
    })

    # Setup provider with resource and sampling
    provider = TracerProvider(
        resource=resource,
        sampler=TraceIdRatioBased(sampling_rate)
    )

    # Setup exporter
    exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
    provider.add_span_processor(BatchSpanProcessor(exporter))

    # Set as global
    trace.set_tracer_provider(provider)

    print(f"✅ Tracing: {service_name} → {endpoint} (sampling={sampling_rate*100}%)")

    return trace.get_tracer(service_name)
