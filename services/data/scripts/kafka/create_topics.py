#!/usr/bin/env python3
"""
Create required Kafka topics using the Confluent Kafka Admin SDK.

Reads bootstrap servers from KAFKA_BOOTSTRAP_SERVERS (default: localhost:9092).
Creates (idempotent):
 - hc.application_external
 - hc.application_dwh
 - hc.application_features
 - more and more, scroll down for more detail

Optionally pass topics via CLI args to create additional topics.
"""

import os
import sys
from typing import List

from confluent_kafka.admin import AdminClient, NewTopic


def create_topics(bootstrap: str, topics: List[str], partitions: int = 8, replication_factor: int = 1) -> None:
    admin = AdminClient({"bootstrap.servers": bootstrap})
    # Fetch existing topics once
    cluster_md = admin.list_topics(timeout=10)
    existing = set(cluster_md.topics.keys())

    to_create = [t for t in topics if t not in existing]
    if not to_create:
        print("No topics to create. All exist.")
        return

    new_topics = [NewTopic(t, num_partitions=partitions, replication_factor=replication_factor) for t in to_create]
    fs = admin.create_topics(new_topics)
    for t, f in fs.items():
        try:
            f.result()
            print(f"✅ Created topic: {t}")
        except Exception as e:
            print(f"❌ Failed to create topic {t}: {e}")


def main():
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    default_topics = [
        os.getenv("FEAST_TOPIC_APP_FEATURES", "hc.application_features"),
        os.getenv("CLICKHOUSE_EXTERNAL", "hc.application_ext_raw"),
        os.getenv("FEAST_TOPIC_EXTERNAL", "hc.application_ext"),
        os.getenv("FEAST_TOPIC_DWH", "hc.application_dwh"),
        os.getenv("BENTOML_SCORING_OUTPUT_TOPIC", "hc.scoring"),
        os.getenv("FEAST_TOPIC_READY_FEATURE","hc.feature_ready")
    ]
    extra = sys.argv[1:]
    topics = default_topics + extra
    print(f"Using Kafka bootstrap servers: {bootstrap}")
    print(f"Ensuring topics exist: {topics}")
    create_topics(bootstrap, topics)


if __name__ == "__main__":
    main()
