#!/usr/bin/env python3
"""
Verify messages are flowing through Kafka topics after Flink deployment.
Used in Jenkins verification stage.

Usage:
    python3 verify_kafka_messages.py \
        --bootstrap broker:29092 \
        --topics hc.application_features,hc.application_ext \
        --timeout 30 \
        --min-messages 10
"""

import argparse
import json
import sys
import time
from kafka import KafkaConsumer, TopicPartition
from typing import List


def check_topic_messages(bootstrap: str, topic: str, timeout_sec: int, min_messages: int) -> bool:
    """Check if topic has minimum number of recent messages."""
    print(f"Checking topic '{topic}' for at least {min_messages} messages...")

    try:
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=bootstrap.split(','),
            auto_offset_reset='latest',
            enable_auto_commit=False,
            consumer_timeout_ms=timeout_sec * 1000,
            value_deserializer=lambda x: json.loads(x.decode('utf-8')) if x else {}
        )

        # Get all partitions for topic
        partitions = consumer.partitions_for_topic(topic)
        if not partitions:
            print(f"WARNING: No partitions found for topic '{topic}'")
            return False

        # Count recent messages across all partitions
        message_count = 0
        start_time = time.time()

        for partition in partitions:
            tp = TopicPartition(topic, partition)
            consumer.assign([tp])

            # Get end offset
            end_offset = consumer.end_offsets([tp])[tp]

            # Seek to end - min_messages (or beginning if not enough messages)
            seek_offset = max(0, end_offset - min_messages)
            consumer.seek(tp, seek_offset)

            # Count messages
            for message in consumer:
                message_count += 1
                if message_count >= min_messages:
                    break

                # Check timeout
                if time.time() - start_time > timeout_sec:
                    break

            if message_count >= min_messages:
                break

        consumer.close()

        print(f"Found {message_count} messages in topic '{topic}'")
        return message_count >= min_messages

    except Exception as e:
        print(f"ERROR checking topic '{topic}': {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Verify Kafka message flow")
    parser.add_argument('--bootstrap', required=True, help='Kafka bootstrap servers')
    parser.add_argument('--topics', required=True, help='Comma-separated list of topics')
    parser.add_argument('--timeout', type=int, default=30, help='Timeout in seconds')
    parser.add_argument('--min-messages', type=int, default=10, help='Minimum messages expected')

    args = parser.parse_args()

    topics = args.topics.split(',')
    all_passed = True

    print(f"\n{'='*60}")
    print(f"Kafka Message Flow Verifier")
    print(f"{'='*60}")
    print(f"Checking {len(topics)} topics")
    print(f"Minimum messages: {args.min_messages}")
    print(f"Timeout: {args.timeout}s")
    print(f"{'='*60}\n")

    for topic in topics:
        topic = topic.strip()
        passed = check_topic_messages(
            args.bootstrap,
            topic,
            args.timeout,
            args.min_messages
        )

        if not passed:
            print(f"FAIL: Topic '{topic}' did not have enough messages\n")
            all_passed = False
        else:
            print(f"PASS: Topic '{topic}' has sufficient messages\n")

    print(f"{'='*60}")
    print(f"Overall: {'PASS' if all_passed else 'FAIL'}")
    print(f"{'='*60}\n")

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
