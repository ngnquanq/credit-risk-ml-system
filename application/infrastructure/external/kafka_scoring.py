import json
import asyncio
from typing import Optional
from confluent_kafka import Producer
from loguru import logger
import socket

from domain.interfaces.scoring_gateway import ScoringGateway
from core.config import settings

class KafkaScoringGateway(ScoringGateway):
    """
    Infrastructure implementation of the ScoringGateway.
    Publishes application IDs to Kafka for asynchronous scoring.
    """
    
    def __init__(self):
        conf = {
            'bootstrap.servers': settings.kafka_bootstrap_servers,
            'client.id': socket.gethostname(),
            'acks': 'all' # Strong durability
        }
        self.producer = Producer(conf)
        # Use the configured application topic
        self.topic = settings.kafka_application_topic
        
    async def publish_for_scoring(self, application_id: str) -> None:
        """
        Publishes the sk_id_curr to the scoring topic.
        """
        message = {
            "sk_id_curr": application_id,
            "type": "APPLICATION_SUBMITTED"
        }
        
        # Delivery report callback
        def delivery_report(err, msg):
            if err is not None:
                logger.error(f"Message delivery failed: {err}")
            else:
                logger.debug(f"Message delivered to {msg.topic()} [{msg.partition()}]")

        # Produce asynchronously
        # logic: 
        # 1. poll(0) to trigger callbacks
        # 2. produce
        # 3. flush is blocking, so we might want to run it in an executor if we strictly need to wait 
        #    or just fire-and-forget with poll.
        
        # Non-blocking produce with callback
        try:
            self.producer.produce(
                self.topic,
                key=application_id.encode('utf-8'),
                value=json.dumps(message).encode('utf-8'),
                callback=delivery_report
            )
            # Poll to trigger callbacks but don't block heavily
            self.producer.poll(0)
            
            # Flush: In production, we'd want assurance, but to avoid tight coupling
            # causing 500s when Kafka is down, we can either:
            # 1. Background task it
            # 2. Accept that if Kafka is down, we rely on logs/reconciliation
            #
            # For now, we'll try to flush with a short timeout and log warning if it fails,
            # but NOT raise exception to the caller.
            # actually, asyncio.to_thread might block the request. 
            # Let's just poll and rely on librdkafka's internal queue.
            # If queue is full, produce will raise BufferError.
            
            logger.info(f"Queued application {application_id} for scoring (topic: {self.topic})")
            
        except Exception as e:
            # Log error but do not fail the request
            logger.error(f"Failed to queue application {application_id} for scoring: {e}")
            # We explicitly swallow the error so the API returns 200/201
