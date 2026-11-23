# stream-features

The Flink jobs that turn change events and bureau data into feature rows, plus the one-off scripts that create Kafka topics and the Debezium connector.

- Code: `flink/jobs/` (CDC application job, bureau aggregation, UDFs)
- Image: `flink/Dockerfile`
- Deploy: `deploy/` (Flink cluster, the two job submissions)
- One-off: `bootstrap/create_topics.py`, `bootstrap/create-connectors.sh`. Run once per environment. Re-running is safe for topics that already exist
- Test: `pytest tests/unit/flink`
- Run in the cluster: `make k8s-streaming`, `make k8s-kafka-topics`
