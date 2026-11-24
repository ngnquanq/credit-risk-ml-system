# stream-features

The Flink jobs that turn change events and bureau data into feature rows, plus the one-off scripts that create Kafka topics and the Debezium connector.

- Code: `flink/jobs/` (CDC application job, bureau aggregation, UDFs)
- Image: `flink/Dockerfile`
- Deploy: `deploy/` (Flink cluster, the two job submissions)
- One-off: `bootstrap/create_topics.py` (skips topics that exist) and `bootstrap/create-connectors.sh`. No make target calls either of them: in the cluster, topics come from the Job in `platform/data/k8s/message-broker/04-kafka-init.yaml` and the connector from the CDC job. Keep these scripts only if you run them by hand
- Test: `pytest tests/unit/flink`
- Run in the cluster: `make k8s-streaming`, `make k8s-kafka-topics`
