#!/usr/bin/env python3
"""
Data Warehouse Features Service

Consumes from: hc.applications.public.loan_applications (CDC topic)
Produces to: hc.application_dwh

For each loan application:
1. Extract sk_id_curr from CDC message
2. Query data warehouse for historical/aggregated features using dwh_client
3. Transform and enrich with DWH-specific features
4. Publish enriched features to hc.application_dwh topic

Todo: some problem with the table schema, remember that we are querying from mart tables
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

from core.config import settings
from services.dwh_client_ch import fetch_all_by_sk_id_curr, get_table_columns, MART_TABLES
from tracing import setup_tracing, extract_or_create_trace_context

# Initialize tracer
tracer = setup_tracing("dwh-features-service", sampling_rate=0.1)


class DWHFeaturesService:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.source_topic = os.getenv("CDC_SOURCE_TOPIC", "hc.applications.public.loan_applications")
        self.sink_topic = os.getenv("SINK_TOPIC_DWH", "hc.application_dwh")
        self.group_id = os.getenv("CONSUMER_GROUP_ID", "dwh-features-service")
        
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
        
        logger.info(f"DWH Features Service initialized")
        logger.info(f"Source topic: {self.source_topic}")
        logger.info(f"Sink topic: {self.sink_topic}")

    async def process_loan_application(self, sk_id_curr: str) -> Optional[Dict[str, Any]]:
        """Query DWH for raw historical data - let Feast handle feature engineering."""
        try:
            sk_id_curr_int = int(sk_id_curr)
            
            # Fetch ALL tables that have SK_ID_CURR in the mart DB
            tables_data = await fetch_all_by_sk_id_curr(sk_id_curr_int)

            # Package raw data; include simple flat fields for Feast ingestion
            prev_cnt = len(tables_data.get("mart_previous_application", []))
            pos_cnt = len(tables_data.get("mart_pos_cash_balance", []))
            cc_cnt = len(tables_data.get("mart_credit_card_balance", []))

            # Schema-driven flattening: always emit all columns (None when missing)
            flat: Dict[str, Any] = {}
            for tbl in MART_TABLES:
                cols = [c for c in get_table_columns(tbl) if c.lower() != "sk_id_curr"]
                rows = tables_data.get(tbl) or []
                row0 = rows[0] if rows else {}
                if row0 is None:
                    row0 = {}
                # Ensure lower-case keys
                row0_lc = {str(k).lower(): v for k, v in row0.items()}
                for col in cols:
                    flat[col] = row0_lc.get(col, None)

            # Flatten record_counts keys to top-level for Feast ingestion
            rc = {k: len(v) for k, v in tables_data.items()}
            dwh_raw_data = {
                "sk_id_curr": sk_id_curr,
                # Use epoch seconds for Feast timestamp alignment
                "ts": time.time(),
                # Include flattened mart metrics
                **flat,
            }
            
            logger.bind(event="dwh_processed").info({
                "sk_id_curr": sk_id_curr,
                "tables_nonempty": [k for k,v in tables_data.items() if v]
            })
            
            return dwh_raw_data
            
        except Exception as e:
            logger.bind(event="dwh_error").error({
                "sk_id_curr": sk_id_curr,
                "error": str(e)
            })
            return None

    def _extract_sk_id_curr_from_cdc(self, cdc_message: Dict[str, Any]) -> Optional[str]:
        """Extract sk_id_curr from CDC message (supports Debezium payload envelope)."""
        try:
            message = cdc_message or {}
            if isinstance(message.get("payload"), dict):
                message = message["payload"]

            if isinstance(message.get("after"), dict):
                rec = message["after"]
            elif isinstance(message.get("before"), dict):
                rec = message["before"]
            else:
                rec = message

            if isinstance(rec, dict) and "sk_id_curr" in rec:
                return str(rec["sk_id_curr"])
            if isinstance(rec, dict) and isinstance(rec.get("value"), dict) and "sk_id_curr" in rec["value"]:
                return str(rec["value"]["sk_id_curr"])
            return None
        except Exception as e:
            logger.error(f"Error extracting sk_id_curr from CDC: {e}")
            return None

    async def run(self):
        """Main service loop."""
        logger.info("Starting DWH Features Service...")
        
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
                    with tracer.start_as_current_span("dwh_features_process", context=parent_context) as span:
                        span.set_attribute("sk_id_curr", sk_id_curr)

                        # Process DWH features
                        dwh_features = await self.process_loan_application(sk_id_curr)

                        if dwh_features:
                            # Inject trace context
                            trace_headers = {}
                            inject(trace_headers)
                            kafka_headers = [(k, v.encode('utf-8') if isinstance(v, str) else v)
                                           for k, v in trace_headers.items()]

                            # Publish to DWH features topic
                            self.producer.produce(
                                topic=self.sink_topic,
                                key=str(sk_id_curr).encode('utf-8'),
                                value=json.dumps(dwh_features).encode('utf-8'),
                                headers=kafka_headers,
                                callback=self._delivery_callback
                            )
                            self.producer.poll(0)
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse CDC message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
        except KeyboardInterrupt:
            logger.info("Shutting down DWH Features Service...")
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
    service = DWHFeaturesService()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
