#!/usr/bin/env python3
"""
Create the Kafka topics listed in contracts/topics/topics.env, using the Confluent Kafka Admin SDK.

Reads bootstrap servers from KAFKA_BOOTSTRAP_SERVERS (default: localhost:9092). Topic names come from
TOPIC_* environment variables when set (the cluster Job gets them from the shared-topics ConfigMap), and
from contracts/topics/topics.env otherwise. Topics that already exist are skipped.

Optionally pass more topic names as CLI arguments.
"""

import os
import sys
from pathlib import Path
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
            print(f"Created topic: {t}")
        except Exception as e:
            print(f"Failed to create topic {t}: {e}")


def registry_topics() -> List[str]:
    """TOPIC_* from the environment, else the shared list in contracts/topics/topics.env."""
    from_env = sorted(v for k, v in os.environ.items() if k.startswith("TOPIC_"))
    if from_env:
        return from_env
    registry = Path(__file__).resolve().parents[3] / "contracts" / "topics" / "topics.env"
    return sorted(line.split("=", 1)[1].strip() for line in registry.read_text().splitlines() if line.startswith("TOPIC_"))


def main():
    bootstrap = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
    default_topics = registry_topics()
    extra = sys.argv[1:]
    topics = default_topics + extra
    print(f"Using Kafka bootstrap servers: {bootstrap}")
    print(f"Ensuring topics exist: {topics}")
    create_topics(bootstrap, topics)


if __name__ == "__main__":
    main()
