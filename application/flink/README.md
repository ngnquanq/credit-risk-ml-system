Flink ETL (PyFlink)
====================

This PyFlink job consumes Debezium CDC events from `loan_applications` and
routes two streams to Kafka topics:

- `hc.application_pii` (limited PII subset)
- `hc.application_features` (non-PII feature subset)

Files
- `jobs/cdc_application_etl.py` — main PyFlink Table API job

Environment variables
- `KAFKA_BOOTSTRAP_SERVERS` (default: `localhost:9092`)
- `CDC_SOURCE_TOPIC` (default: `hc.applications.public.loan_applications`)
- `SINK_TOPIC_PII` (default: `hc.application_pii`)
- `SINK_TOPIC_FEATURES` (default: `hc.application_features`)

Run locally (example)
1) Ensure Kafka is up (`make up-streaming`) and Debezium is configured (`make setup-cdc`).
2) Create sink topics (idempotent):
   `python application/kafka/create_topics.py`
3) Submit the job to a Flink cluster or run with `pyflink` installed:
   `python application/flink/jobs/cdc_application_etl.py`

Note: In production, build a Flink image with Kafka connectors on the classpath
and submit using `flink run -py jobs/cdc_application_etl.py`.

