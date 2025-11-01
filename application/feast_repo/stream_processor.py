#!/usr/bin/env python3
"""
Stream processor for Feast: consume from 3 Kafka topics and materialize to Redis.

Integrates with existing Feast setup defined in this directory.
Uses environment variables from generate_config.py for consistency.

Implements micro-batching for Redis writes to improve throughput and reduce contention.
"""

import json
import os
import queue
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, Any, Optional, List

try:
    from kafka import KafkaConsumer, KafkaProducer
    from loguru import logger
    from feast import FeatureStore
    import pandas as pd
    import redis
except ImportError:
    print("Missing dependencies. Install with: pip install kafka-python loguru 'feast[redis,kafka]' redis")
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
FEATURE_READY_TOPIC = os.getenv("FEAST_TOPIC_READY_FEATURE", "hc.feature_ready")

class FeastStreamProcessor:
    """Stream processor that materializes Kafka data to Feast online store with micro-batching."""

    def __init__(self, repo_path: str = "."):
        """Initialize feature store, Kafka producer, and batching infrastructure."""
        self.repo_path = repo_path

        # Batching configuration
        self.batch_size = int(os.getenv("FEAST_BATCH_SIZE", 50))
        self.batch_timeout_sec = float(os.getenv("FEAST_BATCH_TIMEOUT_MS", 500)) / 1000.0

        # Initialize Feast store using existing configuration
        try:
            self.fs = FeatureStore(repo_path=repo_path)
            logger.info(f"Feast FeatureStore initialized from {repo_path}")

            # Force refresh registry to get latest feature views (avoid stale cache)
            try:
                self.fs.refresh_registry()
                logger.info("Registry refreshed from disk")
            except Exception as refresh_error:
                logger.warning(f"Could not refresh registry: {refresh_error}")

            # Log available feature views for debugging
            try:
                stream_feature_views = [fv.name for fv in self.fs.list_stream_feature_views()]
                logger.info(f"Available StreamFeatureViews: {stream_feature_views}")
                if not stream_feature_views:
                    logger.error("No StreamFeatureViews found! feast-apply may not have completed successfully.")
            except Exception as list_error:
                logger.warning(f"Could not list StreamFeatureViews during init: {list_error}")

        except Exception as e:
            logger.error(f"Failed to initialize Feast: {e}")
            raise

        logger.info(f"Kafka brokers: {KAFKA_BROKERS}")
        logger.info(f"Topics: {TOPICS}")
        logger.info(f"Batching config: size={self.batch_size}, timeout={self.batch_timeout_sec}s")

        # Initialize Kafka producer for feature readiness notifications
        try:
            self.producer = KafkaProducer(
                bootstrap_servers=KAFKA_BROKERS.split(","),
                value_serializer=lambda v: json.dumps(v).encode('utf-8'),
                key_serializer=lambda v: v.encode('utf-8') if isinstance(v, str) else v
            )
            logger.info(f"Kafka producer initialized for topic: {FEATURE_READY_TOPIC}")
        except Exception as e:
            logger.error(f"Failed to initialize Kafka producer: {e}")
            raise

        # Initialize Redis client for coordination (separate from Feast's Redis)
        redis_host = os.getenv("FEAST_REDIS_COORD_HOST", "feast-redis.feature-registry.svc.cluster.local")
        redis_port = int(os.getenv("FEAST_REDIS_COORD_PORT", 6379))
        redis_db = int(os.getenv("FEAST_COORDINATION_DB", 1))  # Use DB 1 for coordination (Feast uses DB 0)
        self.coordination_ttl = int(os.getenv("FEAST_COORDINATION_TTL", 300))  # 5 minutes

        try:
            self.redis_client = redis.Redis(
                host=redis_host,
                port=redis_port,
                db=redis_db,
                decode_responses=True,
                socket_connect_timeout=5,
                socket_timeout=5
            )
            # Test connection
            self.redis_client.ping()
            logger.info(f"Redis coordination client initialized: {redis_host}:{redis_port} DB{redis_db}")
        except Exception as e:
            logger.error(f"Failed to initialize Redis coordination client: {e}")
            raise

        # Load Lua script for atomic coordination
        lua_script_path = os.path.join(os.path.dirname(__file__), "redis_coordination.lua")
        try:
            with open(lua_script_path, 'r') as f:
                lua_script = f.read()
            self.coordination_script = self.redis_client.register_script(lua_script)
            logger.info("Redis coordination Lua script loaded")
        except Exception as e:
            logger.error(f"Failed to load Lua script from {lua_script_path}: {e}")
            raise

        # Per-source batching buffers (thread-safe queues)
        self.batch_buffers = {
            "application": queue.Queue(),
            "external": queue.Queue(),
            "dwh": queue.Queue(),
        }

        # Feature view mapping
        self.feature_view_map = {
            "application": "application_features",
            "external": "external_features",
            "dwh": "dwh_features"
        }

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

    def publish_feature_ready_event(self, sk_id_curr: str, source: str):
        """Publish feature readiness event to Kafka after successful Redis write."""
        try:
            from datetime import datetime
            event = {
                "sk_id_curr": sk_id_curr,
                "source": source,
                "ts": datetime.utcnow().isoformat() + "Z"
            }
            self.producer.send(
                FEATURE_READY_TOPIC,
                key=sk_id_curr,
                value=event
            )
            logger.debug(f"Published feature_ready event for sk_id_curr={sk_id_curr}, source={source}")
        except Exception as e:
            logger.warning(f"Failed to publish feature_ready event for sk_id_curr={sk_id_curr}: {e}")

    def queue_features_for_batch(self, sk_id_curr: str, source: str, features: Dict[str, Any]):
        """Queue features for batched write instead of immediate write."""
        try:
            if not features:
                return

            # Add to batch buffer (non-blocking)
            self.batch_buffers[source].put({
                "sk_id_curr": sk_id_curr,
                "features": features,
                "queued_at": time.time()
            })

        except Exception as e:
            logger.error(f"Failed to queue {source} features for sk_id_curr={sk_id_curr}: {e}")

    def _flush_batch_to_redis(self, batch: List[Dict], source: str):
        """Write batch to Redis and publish individual feature_ready events."""
        if not batch:
            return

        fv_name = self.feature_view_map.get(source)
        if not fv_name:
            logger.warning(f"Unknown source: {source}")
            return

        try:
            # 1. Prepare batch DataFrame
            rows = []
            expected = self._expected_fields_for_source(source)

            for item in batch:
                sk_id_curr = item["sk_id_curr"]
                features = item["features"]

                # Build row
                payload = {name: features.get(name, None) for name in expected}
                data = {
                    "sk_id_curr": sk_id_curr,
                    **payload,
                    "event_timestamp": pd.Timestamp.now(tz="UTC"),
                }

                # Ensure timestamp column
                ts_col = TS_FIELDS.get(source) or "ts"
                if ts_col not in data:
                    data[ts_col] = features.get(ts_col, pd.Timestamp.now(tz="UTC"))

                rows.append(data)

            # 2. Create batch DataFrame (SINGLE DataFrame for all records!)
            df = pd.DataFrame(rows)

            # 3. SINGLE Redis write for entire batch
            batch_write_start = time.time()
            self.fs.write_to_online_store(
                feature_view_name=fv_name,
                df=df
            )
            batch_write_time = (time.time() - batch_write_start) * 1000

            # Calculate throughput
            throughput = len(batch) / (batch_write_time / 1000.0) if batch_write_time > 0 else 0

            logger.info(
                f"Batch wrote {len(batch)} {source} features to Redis in {batch_write_time:.0f}ms "
                f"({throughput:.0f} writes/sec)"
            )

            # 4. Use Redis coordination to track sources and publish only when all 3 are present
            ready_count = 0
            for item in batch:
                sk_id_curr = item["sk_id_curr"]

                try:
                    # Call Lua script atomically: add source to coordination set and get count
                    coord_key = f"feature_coordination:{sk_id_curr}"
                    source_count = self.coordination_script(
                        keys=[coord_key],
                        args=[source, self.coordination_ttl]
                    )

                    # Only publish feature_ready when ALL 3 sources are present
                    if source_count == 3:
                        self.publish_feature_ready_event(sk_id_curr, source)
                        ready_count += 1
                        logger.debug(f"All 3 sources ready for sk_id_curr={sk_id_curr}, published feature_ready")
                    else:
                        logger.debug(f"Source {source} completed for sk_id_curr={sk_id_curr} ({source_count}/3 sources)")

                except Exception as coord_err:
                    logger.error(f"Coordination failed for sk_id_curr={sk_id_curr}: {coord_err}")

            if ready_count > 0:
                logger.info(f"Published {ready_count} feature_ready events (all 3 sources complete)")

        except Exception as e:
            logger.error(f"Failed to flush batch for {source}: {e}")
            # TODO: Consider DLQ for failed batches

    def _batch_flusher_thread(self, source: str):
        """Background thread that flushes batches to Redis."""
        buffer = self.batch_buffers[source]
        logger.info(f"Started batch flusher thread for {source} (size={self.batch_size}, timeout={self.batch_timeout_sec}s)")

        while True:
            batch = []
            batch_start = time.time()

            try:
                # Collect batch (up to batch_size or timeout)
                while len(batch) < self.batch_size:
                    remaining_time = self.batch_timeout_sec - (time.time() - batch_start)

                    if remaining_time <= 0:
                        break  # Timeout reached, flush what we have

                    try:
                        item = buffer.get(timeout=remaining_time)
                        batch.append(item)
                    except queue.Empty:
                        break  # Timeout, flush current batch

                # Flush batch to Redis
                if batch:
                    self._flush_batch_to_redis(batch, source)

            except Exception as e:
                logger.error(f"Error in batch flusher for {source}: {e}")
                time.sleep(1)  # Backoff on error

    def process_kafka_message(self, message, source: str):
        """Process a single Kafka message (queues for batching)."""
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
                logger.debug(f"Queuing {source} message for sk_id_curr={sk_id_curr}")
                self.queue_features_for_batch(sk_id_curr, source, features)
            else:
                logger.debug(f"Skipping {source} message (no valid sk_id_curr or features)")

        except Exception as e:
            logger.error(f"Error processing {source} message: {e}")

    def run_consumer_thread(self, topic: str, source: str):
        """Run Kafka consumer for specific topic in dedicated thread with parallel processing."""
        consumer = None
        executor = None

        # Configurable worker count (default: 20, optimized for Redis throughput)
        max_workers = int(os.getenv("FEAST_MAX_WORKERS", 20))

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
                    logger.info(f"Started {source} consumer for topic: {topic}")

                # Create thread pool for parallel message processing
                if executor is None:
                    executor = ThreadPoolExecutor(
                        max_workers=max_workers,
                        thread_name_prefix=f"FeastWorker-{source}"
                    )
                    cpu_cores = os.cpu_count() or 4
                    logger.info(f"Created thread pool for {source}: {max_workers} workers ({cpu_cores} CPU cores, {max_workers//cpu_cores}x multiplier)")

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
        logger.info("Starting Feast Stream Processor with micro-batching...")

        # Test Feast online store connectivity
        try:
            # Try a simple query to verify setup
            result = self.fs.get_online_features(
                features=["application_features:cnt_children"],
                entity_rows=[{"sk_id_curr": "test_connectivity"}]
            )
            logger.info("Feast online store connectivity verified")
        except Exception as e:
            logger.warning(f"Feast connectivity test failed: {e}")

        # Start batch flusher threads (one per source)
        for source in ["application", "external", "dwh"]:
            thread = threading.Thread(
                target=self._batch_flusher_thread,
                args=(source,),
                daemon=True,
                name=f"BatchFlusher-{source}"
            )
            thread.start()
            logger.info(f"Started batch flusher for {source}")

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

        logger.info(f"Started {len(threads)} consumer threads")

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
