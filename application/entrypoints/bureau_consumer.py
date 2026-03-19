#!/usr/bin/env python3
"""
External Bureau Data Service

Consumes from: hc.applications.public.loan_applications (CDC topic)
Produces to: hc.application_ext_raw (raw bureau data for Flink aggregation)

For each loan application:
1. Extract sk_id_curr from CDC message
2. Query external bureau database using bureau_client (ClickHouse)
3. Publish RAW data to hc.application_ext_raw for Flink processing

Flink Processing (bureau_aggregation_etl.py):
- Consumes from hc.application_ext_raw
- Applies distributed aggregation (60+ features)
- Produces to hc.application_ext
"""

import asyncio
import time
import json
import os
from typing import Any, Dict, Optional

from confluent_kafka import Consumer, Producer
from loguru import logger
from opentelemetry import trace
from opentelemetry.propagate import inject

from infrastructure.external.bureau_client import fetch_bureau_by_loan_id, fetch_external_scores
from core.tracing import setup_tracing, extract_or_create_trace_context

# Initialize tracer
tracer = setup_tracing("external-bureau-service", sampling_rate=0.1)


class ExternalBureauService:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.source_topic = os.getenv("CDC_SOURCE_TOPIC", "hc.applications.public.loan_applications")
        self.raw_topic = os.getenv("RAW_TOPIC_EXT", "hc.application_ext_raw")
        self.group_id = os.getenv("CONSUMER_GROUP_ID", "external-bureau-service")

        # Configure consumer
        self.consumer = Consumer({
            'bootstrap.servers': self.bootstrap_servers,
            'group.id': self.group_id,
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True,
        })

        # Configure producer
        self.producer = Producer({
            'bootstrap.servers': self.bootstrap_servers,
        })

        logger.info(f"External Bureau Service initialized")
        logger.info(f"Source topic: {self.source_topic}")
        logger.info(f"Raw topic: {self.raw_topic} (for Flink aggregation)")

    async def fetch_and_prepare_raw_data(self, sk_id_curr: str) -> Optional[Dict[str, Any]]:
        """Query external bureau data from ClickHouse and prepare for Flink.

        Returns: raw_data dictionary containing:
            - sk_id_curr: Customer ID
            - bureau: List of bureau records
            - bureau_balance: List of bureau balance records
            - external_scores: ext_source_1, ext_source_2, ext_source_3
            - ts: Unix timestamp for Feast
        """
        try:
            sk_id_curr_int = int(sk_id_curr)

            # Fetch bureau data and external scores from ClickHouse
            bureau_data = await fetch_bureau_by_loan_id(sk_id_curr_int)
            external_scores = await fetch_external_scores(sk_id_curr_int)

            # Normalize ext_source_* to float if present (guard against string types)
            for k in ("ext_source_1", "ext_source_2", "ext_source_3"):
                if k in external_scores and external_scores[k] is not None:
                    try:
                        external_scores[k] = float(external_scores[k])
                    except Exception:
                        pass

            # Prepare raw data for Flink aggregation
            raw_data = {
                **bureau_data,  # Contains 'bureau', 'bureau_balance' arrays, and sk_id_curr (int)
                "external_scores": external_scores,
                "sk_id_curr": sk_id_curr,  # Override with string format (e.g., "798498_1041")
                "ts": time.time(),  # Unix timestamp for Feast
            }

            logger.bind(event="bureau_fetched").info({
                "sk_id_curr": sk_id_curr,
                "bureau_count": len(bureau_data.get("bureau", [])),
                "balance_count": len(bureau_data.get("bureau_balance", [])),
                "has_ext_scores": bool(external_scores)
            })

            return raw_data

        except Exception as e:
            logger.bind(event="bureau_error").error({
                "sk_id_curr": sk_id_curr,
                "error": str(e)
            })
            return None

    def _extract_sk_id_curr_from_cdc(self, cdc_message: Dict[str, Any]) -> Optional[str]:
        """Extract sk_id_curr from CDC message.

        Supports plain messages and Debezium envelope with payload.before/after.
        """
        try:
            message = cdc_message or {}
            # Debezium JSON typically nests in payload
            if isinstance(message.get("payload"), dict):
                message = message["payload"]

            # Prefer 'after' (create/update), fallback to 'before' (delete)
            if isinstance(message.get("after"), dict):
                rec = message["after"]
            elif isinstance(message.get("before"), dict):
                rec = message["before"]
            else:
                rec = message

            # Sometimes another layer (e.g., value field)
            if isinstance(rec, dict) and "sk_id_curr" in rec:
                return str(rec["sk_id_curr"])
            if isinstance(rec, dict) and isinstance(rec.get("value"), dict) and "sk_id_curr" in rec["value"]:
                return str(rec["value"]["sk_id_curr"])

            # Log a concise preview for troubleshooting
            logger.debug({
                "cdc_keys": list(cdc_message.keys()) if isinstance(cdc_message, dict) else type(cdc_message).__name__,
                "payload_keys": list((cdc_message.get("payload") or {}).keys()) if isinstance(cdc_message, dict) and isinstance(cdc_message.get("payload"), dict) else None
            })
            return None
        except Exception as e:
            logger.error(f"Error extracting sk_id_curr from CDC: {e}")
            return None

    async def run(self):
        """Main service loop."""
        logger.info("Starting External Bureau Service...")

        try:
            self.consumer.subscribe([self.source_topic])

            while True:
                msg = self.consumer.poll(timeout=1.0)

                if msg is None:
                    continue

                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue

                try:
                    # Parse CDC message
                    cdc_data = json.loads(msg.value().decode('utf-8'))
                    sk_id_curr = self._extract_sk_id_curr_from_cdc(cdc_data)

                    if not sk_id_curr:
                        logger.warning("Could not extract sk_id_curr from CDC message")
                        continue

                    # Extract or create deterministic trace context based on SK_ID_CURR
                    headers_dict = {k: v.decode('utf-8') if isinstance(v, bytes) else v
                                   for k, v in (msg.headers() or [])}
                    parent_context = extract_or_create_trace_context(headers_dict, sk_id_curr)

                    # Start span with parent context (unified trace per SK_ID_CURR)
                    with tracer.start_as_current_span("external_bureau_process", context=parent_context) as span:
                        span.set_attribute("sk_id_curr", sk_id_curr)

                        # Fetch raw bureau data from ClickHouse
                        raw_data = await self.fetch_and_prepare_raw_data(sk_id_curr)

                        # Publish raw data to hc.application_ext_raw (for Flink aggregation)
                        if raw_data:
                            # Inject trace context into headers
                            trace_headers = {}
                            inject(trace_headers)
                            kafka_headers = [(k, v.encode('utf-8') if isinstance(v, str) else v)
                                           for k, v in trace_headers.items()]

                            self.producer.produce(
                                topic=self.raw_topic,
                                key=str(sk_id_curr).encode('utf-8'),
                                value=json.dumps(raw_data).encode('utf-8'),
                                headers=kafka_headers,
                                callback=self._delivery_callback
                            )
                            self.producer.poll(0)  # Non-blocking poll

                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse CDC message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")

        except KeyboardInterrupt:
            logger.info("Shutting down External Bureau Service...")
        finally:
            self.consumer.close()
            self.producer.flush()

    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation."""
        if err is not None:
            logger.error(f'Message delivery failed: {err}')
        else:
            logger.debug(f'Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}')


async def main():
    service = ExternalBureauService()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
