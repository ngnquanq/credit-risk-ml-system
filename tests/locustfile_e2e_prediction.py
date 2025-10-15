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
import random
import time
import psycopg2
from psycopg2.extras import RealDictCursor
from kafka import KafkaConsumer
from datetime import date, datetime, timedelta
from locust import User, task, between, events
from pathlib import Path
import json
from threading import Thread, Event
from queue import Queue
import logging

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
        self.pending_predictions = {}  # {sk_id_curr: submit_timestamp}
        self.stop_event = Event()
        self.consumer_thread = None

    def start(self):
        """Start the Kafka consumer in a background thread."""
        self.consumer_thread = Thread(target=self._consume_predictions, daemon=True)
        self.consumer_thread.start()
        logger.info(f"✓ Prediction monitor started on topic: {self.topic}")

    def stop(self):
        """Stop the Kafka consumer."""
        self.stop_event.set()
        if self.consumer_thread:
            self.consumer_thread.join(timeout=5)

    def register_submission(self, sk_id_curr):
        """Register a loan application submission for latency tracking."""
        self.pending_predictions[sk_id_curr] = time.time()

    def _consume_predictions(self):
        """Background thread that consumes predictions from Kafka."""
        try:
            consumer = KafkaConsumer(
                self.topic,
                bootstrap_servers=self.kafka_bootstrap_servers,
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                consumer_timeout_ms=1000,
                enable_auto_commit=True,
                group_id=f'locust-monitor-{int(time.time())}'
            )

            logger.info(f"Kafka consumer connected to {self.kafka_bootstrap_servers}")

            while not self.stop_event.is_set():
                for message in consumer:
                    try:
                        prediction = message.value
                        sk_id_curr = str(prediction.get('sk_id_curr'))

                        if sk_id_curr in self.pending_predictions:
                            # Calculate end-to-end latency
                            submit_time = self.pending_predictions.pop(sk_id_curr)
                            latency_ms = (time.time() - submit_time) * 1000

                            # Fire Locust event for metrics
                            events.request.fire(
                                request_type="E2E",
                                name="End-to-End Prediction",
                                response_time=latency_ms,
                                response_length=len(json.dumps(prediction)),
                                exception=None,
                                context={}
                            )

                            logger.info(
                                f"✓ Prediction received for {sk_id_curr}: "
                                f"{latency_ms:.0f}ms, decision={prediction.get('decision')}"
                            )

                    except Exception as e:
                        logger.error(f"Error processing prediction: {e}")

        except Exception as e:
            logger.error(f"Kafka consumer error: {e}")
        finally:
            if 'consumer' in locals():
                consumer.close()


# Global prediction monitor (shared across all users)
prediction_monitor = None


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Initialize prediction monitor when test starts."""
    global prediction_monitor

    kafka_bootstrap = environment.host or "localhost:39092"
    # Extract just the hostname:port if URL provided
    if "://" in kafka_bootstrap:
        kafka_bootstrap = kafka_bootstrap.split("://")[1]

    prediction_monitor = PredictionMonitor(
        kafka_bootstrap_servers=kafka_bootstrap,
        topic="hc.scoring"
    )
    prediction_monitor.start()


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Stop prediction monitor when test ends."""
    if prediction_monitor:
        prediction_monitor.stop()
        logger.info("✓ Prediction monitor stopped")


class PredictionPipelineUser(User):
    """
    Simulates a user submitting loan applications directly to PostgreSQL
    and tracks end-to-end prediction latency.
    """

    wait_time = between(1, 3)  # Wait 1-3 seconds between submissions

    customer_ids = []
    db_config = {
        'host': 'localhost',
        'port': 6432,  # PgBouncer connection pooler (transaction mode)
        'database': 'operations',
        'user': 'ops_admin',
        'password': 'ops_password'
    }

    def on_start(self):
        """Load customer IDs from CSV (no persistent connection for transaction pooling)."""
        if not PredictionPipelineUser.customer_ids:
            csv_path = Path(__file__).parent.parent / "data" / "application_train.csv"

            try:
                with open(csv_path, 'r') as f:
                    reader = csv.DictReader(f)
                    # Load 5000 IDs for load testing
                    PredictionPipelineUser.customer_ids = [
                        row['SK_ID_CURR']
                        for row in list(reader)[:5000]
                    ]
                logger.info(f"✓ Loaded {len(PredictionPipelineUser.customer_ids)} customer IDs")
            except FileNotFoundError:
                logger.warning(f"CSV not found, using generated IDs")
                PredictionPipelineUser.customer_ids = [str(i) for i in range(100001, 105001)]

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

        # Add timestamp to make ID unique for repeated tests
        unique_customer_id = f"{customer_id}_{int(time.time() * 1000) % 100000}"

        try:
            # Calculate dates
            age_years = random.randint(25, 65)
            birth_date = date.today() - timedelta(days=age_years * 365)
            employment_years = random.randint(1, 20)
            employment_start_date = date.today() - timedelta(days=employment_years * 365)

            # Open new connection for this transaction (transaction pooling mode)
            connection = psycopg2.connect(**self.db_config)
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

            # Close connection immediately (transaction pooling)
            cursor.close()
            connection.close()

        except Exception as e:
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
    print("  - PostgreSQL running on localhost:5434")
    print("  - Kafka running (for Kafka monitor)")
    print("  - Full pipeline active (CDC, Flink, Feast, KServe)")
    print("")
    print("Run:")
    print("  locust -f tests/locustfile_e2e_prediction.py \\")
    print("         --host=localhost:39092 \\")  # Kafka bootstrap for monitor
    print("         --users 50 --spawn-rate 10 --run-time 5m --headless \\")
    print("         --html reports/e2e_prediction_test.html")
    print("")
    print("="*70)
