"""
End-to-End Prediction Pipeline Load Test

Tests the complete real-time ML pipeline:
1. Insert loan application → PostgreSQL
2. CDC captures change → Kafka
3. Flink processes bureau features
4. Feast materializes to Redis
5. KServe predictor generates prediction
6. Verify prediction appears in output

This measures TRUE end-to-end latency for near real-time predictions.

Usage:
    # Headless mode with metrics
    locust -f tests/locustfile_e2e_prediction.py \
           --users 50 --spawn-rate 10 --run-time 5m --headless \
           --html reports/e2e_prediction_test.html
"""

import csv
import os
import random
import time
import uuid
import sys
import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2.pool import SimpleConnectionPool
from kafka import KafkaConsumer
from kafka.admin import KafkaAdminClient
from datetime import date, datetime, timedelta
from locust import User, task, constant_throughput, events
from locust.runners import WorkerRunner
from pathlib import Path
import json
from threading import Thread, Event, Lock
from queue import Queue
import logging

sys.path.insert(0, str(Path(__file__).resolve().parent))
from e2e_message_parsing import extract_sk_id_curr, unwrap_cloudevent

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PredictionMonitor:
    """
    Monitors Kafka topic for predictions and tracks latency.
    Runs in a background thread to correlate submissions with predictions.
    """

    def __init__(self, kafka_bootstrap_servers, topic):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.topic = topic
        self.topics = ("hc.feature_ready", topic)
        self.group_id = f"locust-monitor-{os.getpid()}-{uuid.uuid4().hex[:8]}"
        self.pending_predictions = {}  # {sk_id_curr: {submitted_at, feature_ready_at, scoring_at}}
        self.submitted_count = 0
        self.feature_ready_count = 0
        self.scoring_count = 0
        self.scoring_observed_count = 0
        self.scoring_unmatched_count = 0
        self.scoring_sample = None
        self.monitor_error = None
        self.sample_path = os.environ.get("E2E_MONITOR_SAMPLE_PATH", "")
        self.lock = Lock()
        self.stop_event = Event()
        self.consumer_thread = None

    def start(self):
        """Start the Kafka consumer in a background thread."""
        self.consumer_thread = Thread(target=self._consume_predictions, daemon=True)
        self.consumer_thread.start()
        logger.info(f"✓ Prediction monitor started on topics: {', '.join(self.topics)}")

    def stop(self):
        """Stop the Kafka consumer."""
        self.stop_event.set()
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)

    def register_submission(self, sk_id_curr):
        """Register a loan application submission for latency tracking."""
        with self.lock:
            self.pending_predictions[sk_id_curr] = {
                "submitted_at": time.time(),
                "feature_ready_at": None,
                "scoring_at": None,
            }
            self.submitted_count += 1

    def _record_feature_ready(self, sk_id_curr):
        observed_at = time.time()
        with self.lock:
            tracked = self.pending_predictions.get(sk_id_curr)
            if not tracked or tracked["feature_ready_at"] is not None:
                return
            tracked["feature_ready_at"] = observed_at
            self.feature_ready_count += 1
            latency_ms = (observed_at - tracked["submitted_at"]) * 1000

        events.request.fire(
            request_type="E2E",
            name="Submit to Feature Ready",
            response_time=latency_ms,
            response_length=0,
            exception=None,
            context={},
        )

    def _record_scoring(self, sk_id_curr, prediction):
        observed_at = time.time()
        with self.lock:
            tracked = self.pending_predictions.get(sk_id_curr)
            if not tracked or tracked["scoring_at"] is not None:
                self.scoring_unmatched_count += 1
                return False

            tracked["scoring_at"] = observed_at
            self.scoring_count += 1
            submit_to_score_ms = (observed_at - tracked["submitted_at"]) * 1000
            feature_ready_at = tracked["feature_ready_at"]
            if feature_ready_at is not None:
                feature_to_score_ms = (observed_at - feature_ready_at) * 1000
            else:
                feature_to_score_ms = None
            self.pending_predictions.pop(sk_id_curr, None)

        events.request.fire(
            request_type="E2E",
            name="End-to-End Prediction",
            response_time=submit_to_score_ms,
            response_length=len(json.dumps(prediction)),
            exception=None,
            context={},
        )
        if feature_to_score_ms is not None:
            events.request.fire(
                request_type="E2E",
                name="Feature Ready to Scoring",
                response_time=feature_to_score_ms,
                response_length=0,
                exception=None,
                context={},
            )

        logger.info(
            f"✓ Prediction received for {sk_id_curr}: "
            f"{submit_to_score_ms:.0f}ms, decision={prediction.get('decision')}"
        )
        return True

    def _redact_payload(self, payload):
        if isinstance(payload, dict):
            return {str(key): self._redact_payload(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._redact_payload(value) for value in payload[:5]]
        if isinstance(payload, (int, float, bool)) or payload is None:
            return payload
        text = str(payload)
        return text if len(text) <= 32 else text[:32] + "...<redacted>"

    def _record_scoring_sample(self, payload, sk_id_curr):
        with self.lock:
            self.scoring_observed_count += 1
            if self.scoring_sample is None:
                self.scoring_sample = {
                    "sk_id_curr_extracted": sk_id_curr,
                    "payload": self._redact_payload(payload),
                }

    def write_scoring_sample(self):
        if not self.sample_path:
            return ""
        with self.lock:
            sample = self.scoring_sample
        if not sample:
            return ""
        path = Path(self.sample_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(sample, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return str(path)

    def delivery_summary(self):
        with self.lock:
            missing_feature_ready = self.submitted_count - self.feature_ready_count
            missing_scoring = self.submitted_count - self.scoring_count
            return {
                "submitted": self.submitted_count,
                "feature_ready": self.feature_ready_count,
                "scoring": self.scoring_count,
                "scoring_observed": self.scoring_observed_count,
                "scoring_unmatched": self.scoring_unmatched_count,
                "monitor_error": self.monitor_error,
                "missing_feature_ready": missing_feature_ready,
                "missing_scoring": missing_scoring,
                "pending": len(self.pending_predictions),
            }

    def _consume_predictions(self):
        """Background thread that consumes predictions from Kafka."""
        while not self.stop_event.is_set():
            consumer = None
            try:
                consumer = KafkaConsumer(
                    *self.topics,
                    bootstrap_servers=self.kafka_bootstrap_servers,
                    value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                    auto_offset_reset='latest',
                    consumer_timeout_ms=1000,
                    enable_auto_commit=True,
                    group_id=self.group_id
                )

                with self.lock:
                    self.monitor_error = None
                logger.info(f"Kafka consumer connected to {self.kafka_bootstrap_servers} as {self.group_id}")

                while not self.stop_event.is_set():
                    for message in consumer:
                        try:
                            payload = message.value
                            body = unwrap_cloudevent(payload)
                            sk_id_curr = extract_sk_id_curr(payload)
                            if message.topic == self.topic:
                                self._record_scoring_sample(payload, sk_id_curr)
                            if not sk_id_curr:
                                continue

                            if message.topic == "hc.feature_ready":
                                self._record_feature_ready(sk_id_curr)
                            elif message.topic == self.topic:
                                prediction = body if isinstance(body, dict) else payload
                                self._record_scoring(sk_id_curr, prediction)

                        except Exception as e:
                            logger.error(f"Error processing prediction: {e}")
            except Exception as e:
                with self.lock:
                    self.monitor_error = str(e)
                if not self.stop_event.is_set():
                    logger.error(f"Kafka consumer error: {e}; retrying in 2s")
                    time.sleep(2)
            finally:
                if consumer is not None:
                    consumer.close()
            if not self.stop_event.is_set():
                time.sleep(1)


class KafkaTopicMonitor:
    """
    Monitors Kafka topics to track message counts and throughput.
    Reports metrics every N seconds to show pipeline health.
    """

    TOPICS = [
        "hc.applications.public.loan_applications",  # CDC source
        "hc.application_features",                   # Flink output
        "hc.application_ext",                        # External service
        "hc.application_dwh",                        # DWH service
        "hc.feature_ready",                          # Feast output
        "hc.scoring",                                # Final predictions
        "hc.scoring.dlq",                            # Prediction failures
    ]

    def __init__(self, kafka_bootstrap_servers, report_interval=10):
        self.kafka_bootstrap_servers = kafka_bootstrap_servers
        self.report_interval = report_interval
        self.stop_event = Event()
        self.monitor_thread = None
        self.initial_offsets = {}
        self.last_offsets = {}

    def start(self):
        """Start the topic monitor in a background thread."""
        self.monitor_thread = Thread(target=self._monitor_topics, daemon=True)
        self.monitor_thread.start()
        logger.info(f"✓ Kafka topic monitor started (reporting every {self.report_interval}s)")

    def stop(self):
        """Stop the topic monitor."""
        self.stop_event.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5)

    def totals_since_start(self):
        """Cumulative messages per topic observed between start and most-recent sample."""
        return {
            t: self.last_offsets.get(t, 0) - self.initial_offsets.get(t, 0)
            for t in self.TOPICS
        }

    def _get_topic_offsets(self, consumer, topic):
        """Get current end offsets for all partitions of a topic."""
        try:
            partitions = consumer.partitions_for_topic(topic)
            if not partitions:
                return {}

            from kafka import TopicPartition
            topic_partitions = [TopicPartition(topic, p) for p in partitions]
            end_offsets = consumer.end_offsets(topic_partitions)

            # Sum across all partitions
            total = sum(end_offsets.values())
            return {topic: total}
        except Exception as e:
            logger.warning(f"Failed to get offsets for {topic}: {e}")
            return {topic: 0}

    def _monitor_topics(self):
        """Background thread that monitors topic sizes."""
        try:
            # Create a consumer just for monitoring (no consumption)
            consumer = KafkaConsumer(
                bootstrap_servers=self.kafka_bootstrap_servers,
                enable_auto_commit=False,
                group_id=None
            )

            logger.info(f"Kafka topic monitor connected to {self.kafka_bootstrap_servers}")

            # Get initial offsets
            for topic in self.TOPICS:
                offsets = self._get_topic_offsets(consumer, topic)
                self.initial_offsets.update(offsets)
                self.last_offsets.update(offsets)

            while not self.stop_event.is_set():
                time.sleep(self.report_interval)

                # Get current offsets
                current_offsets = {}
                for topic in self.TOPICS:
                    offsets = self._get_topic_offsets(consumer, topic)
                    current_offsets.update(offsets)

                # Fire one event per topic with per-interval delta.
                # response_time carries msgs-per-interval so the CSV percentile
                # distribution is a meaningful throughput spread, not a cumulative
                # growth curve. response_length carries msgs/sec.
                for topic in self.TOPICS:
                    current = current_offsets.get(topic, 0)
                    last = self.last_offsets.get(topic, 0)

                    recent_msgs = current - last
                    throughput = recent_msgs / self.report_interval if self.report_interval > 0 else 0

                    topic_short = topic.split('.')[-1][:30]
                    events.request.fire(
                        request_type="Kafka",
                        name=f"📈 msgs/{self.report_interval}s {topic_short}",
                        response_time=recent_msgs,
                        response_length=int(throughput),
                        exception=None,
                        context={}
                    )

                # Update last offsets
                self.last_offsets = current_offsets

        except Exception as e:
            logger.error(f"Kafka topic monitor error: {e}")
        finally:
            if 'consumer' in locals():
                consumer.close()


# Global monitors (shared across all users)
prediction_monitor = None
topic_monitor = None

# Per-process CSV cache and DB pool (initialized once per worker process)
_CUSTOMER_IDS_CACHE = None
_DB_POOL = None


def _load_customer_ids():
    global _CUSTOMER_IDS_CACHE
    if _CUSTOMER_IDS_CACHE is None:
        csv_path = Path(__file__).parent.parent.parent / "data" / "application_train.csv"
        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                _CUSTOMER_IDS_CACHE = [row['SK_ID_CURR'] for row in list(reader)[:5000]]
            logger.info(f"✓ Loaded {len(_CUSTOMER_IDS_CACHE)} customer IDs (cached)")
        except FileNotFoundError:
            logger.warning(f"CSV not found at {csv_path}, using generated IDs")
            _CUSTOMER_IDS_CACHE = [str(i) for i in range(100001, 105001)]
    return _CUSTOMER_IDS_CACHE


def _get_db_pool(db_config):
    global _DB_POOL
    if _DB_POOL is None:
        _DB_POOL = SimpleConnectionPool(minconn=5, maxconn=20, **db_config)
        logger.info("✓ Created per-process psycopg2 SimpleConnectionPool(5, 20)")
    return _DB_POOL


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize monitors when test starts."""
    global prediction_monitor, topic_monitor

    kafka_bootstrap = environment.host or "localhost:9092"
    if "://" in kafka_bootstrap:
        kafka_bootstrap = kafka_bootstrap.split("://")[1]

    # PredictionMonitor runs on every worker: each worker correlates its own
    # submissions against predictions it consumes.
    prediction_monitor = PredictionMonitor(
        kafka_bootstrap_servers=kafka_bootstrap,
        topic="hc.scoring"
    )
    prediction_monitor.start()

    # KafkaTopicMonitor runs only on master/local — offsets are cluster-wide
    # so polling from every worker just duplicates reports.
    if not isinstance(environment.runner, WorkerRunner):
        topic_monitor = KafkaTopicMonitor(
            kafka_bootstrap_servers=kafka_bootstrap,
            report_interval=10
        )
        topic_monitor.start()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Stop monitors and assert the scoring pipeline delivered ≥95% of feature events."""
    if prediction_monitor:
        summary = prediction_monitor.delivery_summary()
        prediction_monitor.stop()
        logger.info("✓ Prediction monitor stopped")
        logger.info("━━━ ID-bounded E2E Delivery ━━━")
        logger.info(f"  submitted            : {summary['submitted']}")
        logger.info(f"  feature_ready matched: {summary['feature_ready']}")
        logger.info(f"  scoring matched      : {summary['scoring']}")
        logger.info(f"  scoring observed     : {summary['scoring_observed']}")
        logger.info(f"  scoring unmatched    : {summary['scoring_unmatched']}")
        if summary["monitor_error"]:
            logger.error(f"  monitor error        : {summary['monitor_error']}")
        logger.info(f"  missing feature_ready: {summary['missing_feature_ready']}")
        logger.info(f"  missing scoring      : {summary['missing_scoring']}")
        if summary["submitted"] > 0:
            scoring_ratio = summary["scoring"] / summary["submitted"]
            logger.info(f"  scoring / submitted  = {scoring_ratio:.3f}")
            if summary["monitor_error"] and summary["scoring_observed"] == 0:
                logger.error(
                    "✗ FAIL: prediction monitor did not consume scoring messages after a Kafka error. "
                    "Treating this as instrumentation-invalid, not pipeline-invalid."
                )
                environment.process_exit_code = 1
            if summary["scoring"] == 0 and summary["scoring_observed"] > 0:
                sample_path = prediction_monitor.write_scoring_sample()
                logger.error(
                    "✗ FAIL: scoring messages were observed but none matched submitted IDs. "
                    "Treating this as instrumentation-invalid, not pipeline-invalid."
                )
                if sample_path:
                    logger.error(f"  redacted scoring sample: {sample_path}")
                environment.process_exit_code = 1
            if scoring_ratio < 0.95:
                logger.error(
                    f"✗ FAIL: ID-bounded scoring delivered only {scoring_ratio:.1%} "
                    "of submitted applications (threshold 95%)."
                )
                environment.process_exit_code = 1

    if topic_monitor:
        totals = topic_monitor.totals_since_start()
        topic_monitor.stop()
        logger.info("✓ Topic monitor stopped")

        feature_ready = totals.get("hc.feature_ready", 0)
        scoring = totals.get("hc.scoring", 0)
        dlq = totals.get("hc.scoring.dlq", 0)

        logger.info("━━━ E2E Scoring Delivery ━━━")
        logger.info(f"  hc.feature_ready : {feature_ready}")
        logger.info(f"  hc.scoring       : {scoring}")
        logger.info(f"  hc.scoring.dlq   : {dlq}")

        if feature_ready > 0:
            ratio = scoring / feature_ready
            dropped = feature_ready - scoring - dlq
            logger.info(f"  scoring / feature_ready = {ratio:.3f}  (offset-derived, silently dropped = {dropped})")
            if ratio < 0.95:
                logger.error(
                    f"✗ WARN: offset-derived scoring ratio is only {ratio:.1%} of feature_ready "
                    f"events. DLQ'd={dlq}, silently dropped={dropped}"
                )
            else:
                logger.info(f"✓ Offset-derived scoring ratio {ratio:.1%} meets 95% threshold")
        else:
            logger.warning("No feature_ready events observed — scoring ratio check skipped")


class PredictionPipelineUser(User):
    """
    Simulates a user submitting loan applications directly to PostgreSQL
    and tracks end-to-end prediction latency.
    """

    # Each user targets N tasks/sec. Override with RPS_PER_USER env var.
    # 50 users × 3 tasks/s = 150 RPS aggregate (matches project SLA target).
    wait_time = constant_throughput(float(os.environ.get("RPS_PER_USER", "3")))

    customer_ids = []
    db_config = {
        'host': os.environ.get('OPS_DB_HOST', 'localhost'),
        'port': int(os.environ.get('OPS_DB_PORT', '5432')),
        'database': os.environ.get('OPS_DB_NAME', 'operations'),
        'user': os.environ.get('OPS_DB_USER', 'ops_admin'),
        'password': os.environ.get('OPS_DB_PASSWORD', ''),
    }

    def on_start(self):
        """Use module-level cache — avoids per-user CSV parse (50× startup cost)."""
        PredictionPipelineUser.customer_ids = _load_customer_ids()

    def on_stop(self):
        """Cleanup (no persistent connection in transaction mode)."""
        pass

    @task
    def submit_loan_application_to_db(self):
        """
        Submit loan application directly to PostgreSQL.
        This triggers CDC → Kafka → Flink → Feast → KServe pipeline.
        """
        start_time = time.time()
        customer_id = random.choice(self.customer_ids)
        connection = None
        cursor = None

        # Add timestamp + random to make ID unique for concurrent tests
        # Uses microseconds + 6-digit random for ~1 trillion unique combinations per second
        unique_customer_id = f"{customer_id}_{int(time.time() * 1000000)}_{random.randint(0, 999999)}"

        try:
            # Calculate dates
            age_years = random.randint(25, 65)
            birth_date = date.today() - timedelta(days=age_years * 365)
            employment_years = random.randint(1, 20)
            employment_start_date = date.today() - timedelta(days=employment_years * 365)

            # Use per-process pool (PgBouncer is in transaction mode — client pooling is safe)
            pool = _get_db_pool(self.db_config)
            connection = pool.getconn()
            cursor = connection.cursor()

            # Insert loan application
            insert_query = """
                INSERT INTO public.loan_applications (
                    sk_id_curr, code_gender, birth_date, cnt_children,
                    amt_income_total, amt_credit, amt_annuity, amt_goods_price,
                    name_contract_type, name_income_type, name_education_type,
                    name_family_status, name_housing_type, employment_start_date,
                    occupation_type, organization_type,
                    flag_mobil, flag_emp_phone, flag_work_phone,
                    flag_phone, flag_email, flag_own_car, flag_own_realty,
                    own_car_age
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                )
            """

            values = (
                unique_customer_id,
                random.choice(['M', 'F']),
                birth_date,
                random.randint(0, 3),
                random.uniform(50000, 500000),
                random.uniform(100000, 1000000),
                random.uniform(5000, 50000),
                random.uniform(100000, 1000000),
                random.choice(['Cash loans', 'Revolving loans']),
                random.choice(['Working', 'Commercial associate', 'Pensioner']),
                random.choice(['Secondary / secondary special', 'Higher education']),
                random.choice(['Single / not married', 'Married']),
                random.choice(['House / apartment', 'Rented apartment', 'With parents', 'Municipal apartment', 'Office apartment', 'Co-op apartment']),
                employment_start_date,
                random.choice(['Laborers', 'Core staff', 'Managers', None]),
                random.choice(['Business Entity Type 3', 'School', None]),
                1, 0, 0, 0, 1, random.randint(0, 1), random.randint(0, 1),
                random.randint(0, 20) if random.random() > 0.5 else None
            )

            cursor.execute(insert_query, values)
            connection.commit()

            # Register for prediction monitoring
            if prediction_monitor:
                prediction_monitor.register_submission(unique_customer_id)

            # Record database insertion latency
            db_latency_ms = (time.time() - start_time) * 1000

            events.request.fire(
                request_type="PostgreSQL",
                name="Insert Loan Application",
                response_time=db_latency_ms,
                response_length=0,
                exception=None,
                context={}
            )

        except Exception as e:
            if connection:
                try:
                    connection.rollback()
                except Exception:
                    logger.exception("Failed to roll back failed insert transaction")

            latency_ms = (time.time() - start_time) * 1000
            events.request.fire(
                request_type="PostgreSQL",
                name="Insert Loan Application",
                response_time=latency_ms,
                response_length=0,
                exception=e,
                context={}
            )
            logger.error(f"Failed to insert application: {e}")
        finally:
            if cursor:
                cursor.close()
            if connection:
                pool.putconn(connection)


if __name__ == "__main__":
    print("="*70)
    print("  End-to-End Prediction Pipeline Load Test")
    print("="*70)
    print("")
    print("This test measures:")
    print("  1. PostgreSQL insert latency")
    print("  2. End-to-end prediction latency (PostgreSQL → Prediction)")
    print("")
    print("Prerequisites:")
    print("  - Port-forward PgBouncer: kubectl port-forward -n data-services svc/ops-pgbouncer 6432:6432")
    print("  - Port-forward Kafka:    kubectl port-forward -n data-services svc/kafka-broker 9092:9092")
    print("  - Full pipeline active (CDC, Flink, Feast, KServe)")
    print("")
    print("Run:")
    print("  locust -f tests/locustfile_e2e_prediction.py \\")
    print("         --host=localhost:9092 \\")  # Kafka bootstrap for monitor
    print("         --users 50 --spawn-rate 10 --run-time 5m --headless \\")
    print("         --html reports/e2e_prediction_test.html")
    print("")
    print("="*70)
