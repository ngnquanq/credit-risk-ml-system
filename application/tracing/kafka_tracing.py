"""
Kafka utilities with trace context propagation
"""

from opentelemetry import trace
from opentelemetry.propagate import inject, extract
from kafka import KafkaProducer, KafkaConsumer
import json


class TracingKafkaProducer:
    """Kafka producer that propagates trace context in headers"""

    def __init__(self, bootstrap_servers, **kwargs):
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            **kwargs
        )
        self.tracer = trace.get_tracer(__name__)

    def send_traced(self, topic: str, value: dict, sk_id: str = None):
        """Send message with trace context"""
        with self.tracer.start_as_current_span(f"kafka_publish") as span:
            span.set_attribute("messaging.system", "kafka")
            span.set_attribute("messaging.destination", topic)
            if sk_id:
                span.set_attribute("sk_id_curr", sk_id)

            # Inject trace context into headers
            headers = {}
            inject(headers)

            # Convert to Kafka header format
            kafka_headers = [(k, str(v).encode('utf-8')) for k, v in headers.items()]

            # Send
            self.producer.send(topic, value=value, headers=kafka_headers)

    def close(self):
        self.producer.close()


class TracingKafkaConsumer:
    """Kafka consumer that extracts trace context from headers"""

    def __init__(self, topic, bootstrap_servers, group_id, **kwargs):
        self.consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            **kwargs
        )
        self.tracer = trace.get_tracer(__name__)

    def consume_traced(self):
        """
        Consume messages with trace context

        Yields:
            tuple: (message_value, parent_context)
        """
        for message in self.consumer:
            # Extract trace context from headers
            headers_dict = {
                k.decode('utf-8'): v.decode('utf-8')
                for k, v in (message.headers or [])
            }

            # Extract parent context
            parent_context = extract(headers_dict)

            yield message.value, parent_context

    def close(self):
        self.consumer.close()
