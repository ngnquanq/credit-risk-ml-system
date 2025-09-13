"""
Kafka consumer (confluent-kafka) that listens for bureau request events
and queries the bureau DB, publishing results to a response topic.

Message contract (request topic, JSON):
{
  "loan_id": 123456,            # maps to sk_id_curr
  "request_id": "<uuid>",      # optional pass-through
  "source": "<string>"         # optional, for observability
}

Message contract (response topic, JSON):
{
  "loan_id": 123456,
  "request_id": "<uuid>",
  "status": "ok" | "not_found" | "error",
  "records": <int>,            # number of bureau records
  "bureau": [ ... ],           # rows from bureau
  "bureau_balance": [ ... ],   # rows from bureau_balance
  "error": "<message>"        # only on error
}
"""

import json
import threading
import time
from typing import Optional, Any, Dict

from loguru import logger
from confluent_kafka import Consumer, Producer, KafkaException

from core.config import settings
from .bureau_client import fetch_bureau_by_loan_id
from decimal import Decimal
from datetime import datetime, date


class BureauKafkaWorker:
    """Background Kafka worker for bureau requests using confluent-kafka.

    Runs a polling loop in a dedicated thread to avoid blocking the event loop.
    """

    def __init__(self) -> None:
        self._consumer: Optional[Consumer] = None
        self._producer: Optional[Producer] = None
        self._thread: Optional[threading.Thread] = None
        self._stopping = threading.Event()

    async def start(self) -> None:
        if not settings.enable_kafka_consumer:
            logger.info("Kafka consumer disabled by config (enable_kafka_consumer=false)")
            return

        consumer_conf = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
            "group.id": settings.kafka_consumer_group,
            "auto.offset.reset": "earliest",
            "enable.auto.commit": True,
        }
        producer_conf = {
            "bootstrap.servers": settings.kafka_bootstrap_servers,
        }

        self._consumer = Consumer(consumer_conf)
        self._producer = Producer(producer_conf)
        self._consumer.subscribe([settings.kafka_request_topic])

        logger.info(
            f"Starting Kafka consumer group={settings.kafka_consumer_group} topic={settings.kafka_request_topic}"
        )
        self._thread = threading.Thread(target=self._run_loop, name="bureau-kafka-consumer", daemon=True)
        self._thread.start()

    async def stop(self) -> None:
        self._stopping.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10)
        if self._consumer:
            try:
                self._consumer.close()
            except Exception:
                pass
        if self._producer:
            try:
                self._producer.flush(5)
            except Exception:
                pass
        logger.info("Kafka consumer stopped")

    def _run_loop(self) -> None:
        assert self._consumer is not None
        assert self._producer is not None
        while not self._stopping.is_set():
            try:
                msg = self._consumer.poll(1.0)
                if msg is None:
                    continue
                if msg.error():
                    raise KafkaException(msg.error())
                self._handle_message(msg)
            except Exception as e:
                logger.exception(f"Kafka consumer loop error: {e}")
                time.sleep(1)

    def _handle_message(self, msg: Any) -> None:
        try:
            raw = msg.value()
            payload = json.loads(raw.decode("utf-8")) if isinstance(raw, (bytes, bytearray)) else json.loads(raw)
        except Exception as e:
            logger.error(f"Invalid JSON payload on topic {msg.topic()}: {e}")
            return

        loan_id = payload.get("loan_id")
        request_id = payload.get("request_id")
        source = payload.get("source")
        logger.bind(event="bureau_request").info(
            {"loan_id": loan_id, "request_id": request_id, "source": source}
        )

        if loan_id is None:
            logger.error("Missing loan_id in request payload")
            return

        try:
            # Call async DB fetch from a thread using asyncio.run? Keep it simple by using a helper.
            # We import here to avoid event loop complications; run a nested loop for the async function.
            import asyncio

            data = asyncio.run(fetch_bureau_by_loan_id(int(loan_id)))
            records = len(data.get("bureau", []))
            status = "ok" if records > 0 else "not_found"
            response: Dict[str, Any] = {
                "loan_id": loan_id,
                "request_id": request_id,
                "status": status,
                "records": records,
                "bureau": data.get("bureau", []),
                "bureau_balance": data.get("bureau_balance", []),
            }
        except Exception as e:
            logger.exception(f"Error querying bureau for loan_id={loan_id}: {e}")
            response = {
                "loan_id": loan_id,
                "request_id": request_id,
                "status": "error",
                "error": str(e),
            }

        # Publish response
        try:
            self._producer.produce(
                topic=settings.kafka_response_topic,
                value=json.dumps(response, default=_json_default).encode("utf-8"),
            )
            self._producer.poll(0)
            logger.bind(event="bureau_response").info(
                {
                    "loan_id": loan_id,
                    "request_id": request_id,
                    "status": response.get("status"),
                    "records": response.get("records"),
                }
            )
        except Exception as e:
            logger.exception(
                f"Failed to publish bureau response for loan_id={loan_id}: {e}"
            )


def _json_default(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    return str(obj)


# Singleton worker for app lifecycle control
worker = BureauKafkaWorker()