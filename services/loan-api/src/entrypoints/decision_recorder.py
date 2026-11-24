#!/usr/bin/env python3
"""Decision recorder consumer (E5, E15).

Consumes:
  hc.scoring        decision events from the scoring service
  hc.feature_timeout readiness timeouts (E3)            -> manual_review, features_incomplete
  hc.scoring.dlq    scoring requests that failed retries -> manual_review, scoring_unavailable

Writes one application_status_log row per event (idempotent on event_id) and commits
the Kafka offset only after the row is written. Malformed events go to hc.decisions.dlq.
"""

from __future__ import annotations

import json
import os
import signal

from confluent_kafka import Consumer, Producer
from loguru import logger
from core.log_setup import setup_logging

from decisions.recorder import DecisionRecorder
from decisions.status_log import PostgresStatusLogWriter

SCORING_TOPIC = os.getenv("SCORING_TOPIC", "hc.scoring")
TIMEOUT_TOPIC = os.getenv("TIMEOUT_TOPIC", "hc.feature_timeout")
SCORING_DLQ_TOPIC = os.getenv("SCORING_DLQ_TOPIC", "hc.scoring.dlq")
RECORDER_DLQ_TOPIC = os.getenv("RECORDER_DLQ_TOPIC", "hc.decisions.dlq")


def _connect():
    import psycopg

    return psycopg.connect(
        host=os.getenv("OPS_DB_HOST", "ops-postgres"),
        port=int(os.getenv("OPS_DB_PORT", "5432")),
        dbname=os.getenv("OPS_DB_NAME", "operations"),
        user=os.environ["OPS_DB_USER"],
        password=os.environ["OPS_DB_PASSWORD"],
    )


def _header(msg, name: str) -> str | None:
    for key, value in msg.headers() or []:
        if key == name and value is not None:
            return value.decode() if isinstance(value, bytes) else str(value)
    return None


def dispatch(recorder: DecisionRecorder, msg) -> str:
    """Route one Kafka message to the recorder; returns the RecordResult name."""
    event = json.loads(msg.value())
    topic = msg.topic()
    if topic == SCORING_TOPIC:
        result = recorder.handle_decision(event)
    elif topic == TIMEOUT_TOPIC:
        result = recorder.handle_timeout(event)
    elif topic == SCORING_DLQ_TOPIC:
        # Dead letters carry the original feature_ready payload; derive a stable id from the message.
        event_id = _header(msg, "ce_id") or _header(msg, "ce-id") or f"dlq:{msg.partition()}:{msg.offset()}"
        event.setdefault("error", _header(msg, "ce_knativeerrordata") or _header(msg, "ce_knativeerrorcode"))
        result = recorder.handle_dead_letter(event, event_id)
    else:  # pragma: no cover - subscription guarantees the topic
        raise ValueError(f"Unexpected topic {topic}")
    return result.value


def main() -> None:
    setup_logging("decision-recorder")
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    consumer = Consumer({
        "bootstrap.servers": bootstrap,
        "group.id": os.getenv("CONSUMER_GROUP_ID", "decision-recorder"),
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,
    })
    producer = Producer({"bootstrap.servers": bootstrap, "acks": "all"})
    recorder = DecisionRecorder(PostgresStatusLogWriter(_connect))
    consumer.subscribe([SCORING_TOPIC, TIMEOUT_TOPIC, SCORING_DLQ_TOPIC])

    running = True

    def _stop(*_):
        nonlocal running
        running = False

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("Decision recorder started")

    try:
        while running:
            msg = consumer.poll(1.0)
            if msg is None:
                continue
            if msg.error():
                logger.error(f"Kafka error: {msg.error()}")
                continue
            try:
                result = dispatch(recorder, msg)
                logger.bind(event="decision_recorded").info(
                    {"topic": msg.topic(), "partition": msg.partition(), "offset": msg.offset(), "result": result}
                )
            except (ValueError, KeyError, json.JSONDecodeError) as exc:
                # Poison message: park it and move on.
                producer.produce(RECORDER_DLQ_TOPIC, value=msg.value(), headers=[("error", str(exc)[:500])])
                producer.flush(5)
                logger.warning(f"Malformed event sent to {RECORDER_DLQ_TOPIC}: {exc}")
            # Database errors propagate: the offset is not committed and the pod restarts.
            consumer.commit(message=msg, asynchronous=False)
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
