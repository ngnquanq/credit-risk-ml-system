#!/usr/bin/env python3
"""
Stream processor for Feast: consume from 3 Kafka topics and materialize to Redis.

Integrates with existing Feast setup defined in this directory.
Uses environment variables from generate_config.py for consistency.
"""

import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List

try:
    from kafka import KafkaConsumer
    from loguru import logger
    from feast import FeatureStore
    import pandas as pd
except ImportError:
    print("Missing dependencies. Install with: pip install kafka-python loguru 'feast[redis,kafka]'")
    sys.exit(1)

# Use same environment variables as generate_config.py for consistency
KAFKA_BROKERS = os.getenv("FEAST_KAFKA_BROKERS", "broker:29092")
TOPICS = {
    "application": "hc.application_features",  # From Flink
    "external": "hc.application_ext",         # From external service  
    "dwh": "hc.application_dwh"               # From DWH service
}
TS_FIELDS = {
    "application": os.getenv("FEAST_TS_FIELD_APP", "ts"),
    "external": os.getenv("FEAST_TS_FIELD_EXT", "ts"),
    "dwh": os.getenv("FEAST_TS_FIELD_DWH", "ts"),
}

class FeastStreamProcessor:
    """Stream processor that materializes Kafka data to Feast online store."""
    
    def __init__(self, repo_path: str = "."):
        self.repo_path = repo_path
        
        # Initialize Feast store using existing configuration
        try:
            self.fs = FeatureStore(repo_path=repo_path)
            logger.info(f"✓ Feast FeatureStore initialized from {repo_path}")
            
            # Log available feature views for debugging
            try:
                stream_feature_views = [fv.name for fv in self.fs.list_stream_feature_views()]
                logger.info(f"Available StreamFeatureViews: {stream_feature_views}")
            except Exception as list_error:
                logger.warning(f"Could not list StreamFeatureViews during init: {list_error}")

        except Exception as e:
            logger.error(f"✗ Failed to initialize Feast: {e}")
            raise
            
        logger.info(f"Kafka brokers: {KAFKA_BROKERS}")
        logger.info(f"Topics: {TOPICS}")

    def extract_sk_id_curr_and_features(self, message: Dict[str, Any]) -> tuple[Optional[str], Dict[str, Any]]:
        """Extract sk_id_curr and features from Kafka message (handles CDC format)."""
        try:
            # Handle Debezium CDC envelope
            if "payload" in message:
                payload = message["payload"]
                record = payload.get("after") or payload.get("before") or payload
            else:
                record = message
                
            if not isinstance(record, dict):
                return None, {}
                
            sk_id_curr = record.get("sk_id_curr")
            if not sk_id_curr:
                return None, {}
                
            # Extract all features except entity key
            features = {k: v for k, v in record.items() if k != "sk_id_curr"}
            
            return str(sk_id_curr), features
            
        except Exception as e:
            logger.warning(f"Failed to parse message: {e}")
            return None, {}

    def _expected_fields_for_source(self, source: str) -> List[str]:
        """Return expected feature field names for a given source using FV schemas."""
        try:
            # Import local FV definitions to discover schema
            from feature_views import (
                fv_application_features,
                fv_external,
                fv_dwh,
            )
            mapping = {
                "application": fv_application_features,
                "external": fv_external,
                "dwh": fv_dwh,
            }
            fv = mapping.get(source)
            if not fv:
                return []
            # schema is a list of feast.Field; first element is entity key sk_id_curr which we exclude
            names = [f.name for f in getattr(fv, "schema", []) if getattr(f, "name", None)]
            return [n for n in names if n != "sk_id_curr"]
        except Exception:
            return []

    def write_features_to_online_store(self, sk_id_curr: str, source: str, features: Dict[str, Any]):
        """Write features to Feast online store using proper SDK method."""
        try:
            if not features:
                return
                
            # Prepare DataFrame for Feast (entity + features + timestamp)
            expected = self._expected_fields_for_source(source)
            # Keep only expected columns and fill missing ones with None, to match FV schema
            payload: Dict[str, Any] = {}
            for name in expected:
                payload[name] = features.get(name, None)

            data = {
                "sk_id_curr": sk_id_curr,
                **payload,
                "event_timestamp": pd.Timestamp.now(tz="UTC"),
            }
            # Ensure the stream timestamp column exists for Feast 0.34 projections
            ts_col = TS_FIELDS.get(source) or "ts"
            if ts_col not in data:
                msg_ts = features.get(ts_col)
                data[ts_col] = pd.Timestamp.now(tz="UTC") if msg_ts is None else msg_ts
            df = pd.DataFrame([data])
            
            # Get feature view name based on source
            feature_view_map = {
                "application": "application_features",
                "external": "external_features",
                "dwh": "dwh_features"
            }
            
            fv_name = feature_view_map.get(source)
            if not fv_name:
                logger.warning(f"Unknown source: {source}")
                return
                
            # Write to online store using Feast SDK
            self.fs.write_to_online_store(
                feature_view_name=fv_name,
                df=df
            )
            
            logger.info(f"✓ Wrote {source} features for sk_id_curr={sk_id_curr} ({len(features)} features)")
            
        except Exception as e:
            logger.error(f"Failed to write {source} features for sk_id_curr={sk_id_curr}: {e}")

    def process_kafka_message(self, message, source: str):
        """Process a single Kafka message."""
        try:
            # Parse message value
            if hasattr(message, 'value'):
                data = message.value
            else:
                data = message
                
            if isinstance(data, (str, bytes)):
                data = json.loads(data)
                
            sk_id_curr, features = self.extract_sk_id_curr_and_features(data)
            
            if sk_id_curr and features:
                logger.info(f"Processing {source} message for sk_id_curr={sk_id_curr}")
                self.write_features_to_online_store(sk_id_curr, source, features)
            else:
                logger.debug(f"Skipping {source} message (no valid sk_id_curr or features)")
                
        except Exception as e:
            logger.error(f"Error processing {source} message: {e}")

    def run_consumer_thread(self, topic: str, source: str):
        """Run Kafka consumer for specific topic in dedicated thread with parallel processing."""
        consumer = None
        executor = None

        # Configurable worker count (default: 50, or from environment)
        max_workers = int(os.getenv("FEAST_MAX_WORKERS", 50))

        while True:
            try:
                if consumer is None:
                    consumer = KafkaConsumer(
                        topic,
                        bootstrap_servers=KAFKA_BROKERS.split(","),
                        group_id=f"feast-materializer-{source}",
                        auto_offset_reset='latest',
                        enable_auto_commit=True,
                        consumer_timeout_ms=10000,  # 10 second timeout
                        value_deserializer=lambda x: json.loads(x.decode('utf-8')) if x else {}
                    )
                    logger.info(f"✓ Started {source} consumer for topic: {topic}")

                # Create thread pool for parallel message processing
                if executor is None:
                    executor = ThreadPoolExecutor(
                        max_workers=max_workers,
                        thread_name_prefix=f"FeastWorker-{source}"
                    )
                    cpu_cores = os.cpu_count() or 4
                    logger.info(f"✓ Created thread pool for {source}: {max_workers} workers ({cpu_cores} CPU cores, {max_workers//cpu_cores}x multiplier)")

                # Consume messages and process in parallel (non-blocking!)
                for message in consumer:
                    # Submit to thread pool - returns immediately without waiting
                    executor.submit(self.process_kafka_message, message, source)

            except Exception as e:
                logger.error(f"Consumer error for {source}: {e}")
                if consumer:
                    consumer.close()
                    consumer = None
                if executor:
                    executor.shutdown(wait=False)
                    executor = None
                time.sleep(5)  # Wait before reconnecting

    def start(self):
        """Start stream processor with consumer threads for all topics."""
        logger.info("Starting Feast Stream Processor...")
        
        # Test Feast online store connectivity
        try:
            # Try a simple query to verify setup
            result = self.fs.get_online_features(
                features=["application_features:cnt_children"],
                entity_rows=[{"sk_id_curr": "test_connectivity"}]
            )
            logger.info("✓ Feast online store connectivity verified")
        except Exception as e:
            logger.warning(f"⚠ Feast connectivity test failed: {e}")
        
        # Start consumer threads
        threads = []
        for source, topic in TOPICS.items():
            thread = threading.Thread(
                target=self.run_consumer_thread,
                args=(topic, source),
                daemon=True,
                name=f"Consumer-{source}"
            )
            thread.start()
            threads.append(thread)
            
        logger.info(f"✓ Started {len(threads)} consumer threads")
        
        # Main monitoring loop
        try:
            while True:
                time.sleep(30)
                alive_threads = sum(1 for t in threads if t.is_alive())
                logger.info(f"Status: {alive_threads}/{len(threads)} consumers running")
                
        except KeyboardInterrupt:
            logger.info("Shutting down stream processor...")


def main():
    """Main entry point - run from feast directory."""
    # Ensure we're in the feast directory for proper repo path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)
    
    # Initialize and start processor
    processor = FeastStreamProcessor(repo_path=".")
    processor.start()


if __name__ == "__main__":
    main()
